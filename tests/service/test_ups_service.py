import unittest
from unittest.mock import MagicMock, patch
from crac_protobuf.chart_pb2 import ChartStatus
from crac_protobuf.emergency_closure_pb2 import (
    EmergencyClosure,  # type: ignore
    EmergencyClosureStatus,  # type: ignore
)
from crac_protobuf.ups_pb2 import BatteryStatus, UpsStatus
from crac_server.component.ups import ups
from crac_server.converter.chart_config import ChartConfigError
from crac_server.service.ups_service import UpsService


SECTIONS = {
    "battery_charge": {"scale": "0..100", "warning": "35..50", "danger": "..35"},
    "input_voltage": {"scale": "0..250", "warning": "..209", "danger": "241.5.."},
    "output_current": {"scale": "0..20", "danger": "8.."},
}


def getkeys_side_effect(enabled):
    def side_effect(name):
        if name == "ups_metrics":
            return enabled
        return list(SECTIONS[name])
    return side_effect


def getvalue_side_effect(ups_list="apc-3000,cyberpower"):
    def side_effect(key, section="automazione"):
        if (key, section) == ("ups_list", "ups"):
            return ups_list
        return SECTIONS[section][key]
    return side_effect



def setUpModule():
    """These tests patch Config for the UPS: the emergency closure, built on
    first use, must not read its timeouts through that patch."""
    patcher = patch("crac_server.service.ups_service.emergency_closure")
    patcher.start().return_value.state.return_value = EmergencyClosure()
    unittest.addModuleCleanup(patcher.stop)


class TestUpsServiceStartupValidation(unittest.TestCase):
    def test_init_raises_when_an_enabled_metric_has_a_broken_threshold(self):
        def broken(key, section="automazione"):
            if section == "battery_charge" and key == "scale":
                return ""
            return getvalue_side_effect()(key, section)

        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=broken):
            with self.assertRaises(ChartConfigError):
                UpsService()

    def test_init_raises_when_a_band_can_never_be_reached(self):
        def unreachable_band(key, section="automazione"):
            if section == "battery_charge" and key == "danger":
                return "50..35"
            return getvalue_side_effect()(key, section)

        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=unreachable_band):
            with self.assertRaises(ChartConfigError):
                UpsService()

    def test_init_raises_on_a_metric_the_service_cannot_chart(self):
        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "battery_voltage": "battery.voltage"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "battery_voltage"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()):
            with self.assertRaises(RuntimeError) as ctx:
                UpsService()
        self.assertIn("battery_voltage", str(ctx.exception))

    def test_init_accepts_ups_status_when_the_battery_chart_exists(self):
        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "ups_status": "ups.status"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "ups_status"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()):
            UpsService()

    def test_init_raises_when_ups_status_has_no_battery_chart_to_ride_on(self):
        with patch("crac_server.service.ups_service.Config.get_section", return_value={"input_voltage": "input.voltage", "ups_status": "ups.status"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["input_voltage", "ups_status"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()):
            with self.assertRaises(RuntimeError) as ctx:
                UpsService()
        self.assertIn("ups_status", str(ctx.exception))
        self.assertIn("battery_charge", str(ctx.exception))

    def test_init_raises_on_a_metric_left_empty(self):
        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "input_voltage"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()):
            with self.assertRaises(RuntimeError) as ctx:
                UpsService()
        self.assertIn("input_voltage", str(ctx.exception))

    def test_init_explains_that_the_section_is_missing(self):
        with patch("crac_server.service.ups_service.Config.get_section", side_effect=KeyError("ups_metrics")):
            with self.assertRaises(RuntimeError) as ctx:
                UpsService()
        self.assertIn("ups_metrics", str(ctx.exception))

    def test_init_ignores_thresholds_of_metrics_not_enabled(self):
        def missing_current_config(name):
            if name == "output_current":
                raise KeyError(name)
            return getkeys_side_effect(["battery_charge", "input_voltage"])(name)

        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "input_voltage": "input.voltage"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=missing_current_config), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()):
            UpsService()


class TestUpsListValidation(unittest.TestCase):
    def _build_with(self, ups_list):
        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect(ups_list)):
            return UpsService()._configured_devices()

    def test_strips_the_spaces_around_names(self):
        self.assertEqual(["apc-3000", "cyberpower"], self._build_with("apc-3000, cyberpower"))

    def test_raises_on_an_empty_entry(self):
        with self.assertRaises(RuntimeError):
            self._build_with("apc-3000,")

    def test_raises_on_duplicated_devices(self):
        with self.assertRaises(RuntimeError):
            self._build_with("apc-3000,apc-3000")

    def test_raises_when_no_device_is_configured(self):
        with self.assertRaises(RuntimeError):
            self._build_with("")


class TestUpsService(unittest.TestCase):

    def setUp(self):
        self._original_status_for = ups().status_for
        self._patches = [
            patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "input_voltage": "input.voltage", "ups_status": "ups.status"}),
            patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "input_voltage", "ups_status"])),
            patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()),
        ]
        for p in self._patches:
            p.start()
        self.ups_service = UpsService()

    def tearDown(self):
        ups().status_for = self._original_status_for
        for p in self._patches:
            p.stop()

    def _ok_reading(self):
        return {"input_voltage": "220", "battery_charge": "80"}

    def test_get_status_all_devices_ok(self):
        ups().status_for = MagicMock(side_effect=lambda device: self._ok_reading())

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        self.assertEqual(4, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, response.status)

    def test_every_response_carries_the_closure_state(self):
        state = EmergencyClosure(status=EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_BLOCKED)
        for reading in (self._ok_reading, ConnectionError("unreachable")):
            with self.subTest(reading=reading):
                ups().status_for = MagicMock(side_effect=reading if isinstance(reading, Exception) else lambda device: reading())
                with patch("crac_server.service.ups_service.emergency_closure") as closure:
                    closure.return_value.state.return_value = state

                    response = self.ups_service.GetStatus(None, None)

                self.assertEqual(state, response.emergency_closure)

    def test_get_status_builds_current_chart_when_present(self):
        ups().status_for = MagicMock(return_value={**self._ok_reading(), "output_current": "3"})

        response = self.ups_service.GetStatus(None, None)

        urns = [chart.chart.urn for chart in response.charts]
        self.assertIn("ups.apc-3000.chart.current", urns)
        self.assertEqual(6, len(response.charts))

    def _battery_chart(self, response, device="apc-3000"):
        return next(chart for chart in response.charts if chart.chart.urn == f"ups.{device}.chart.battery")

    def test_battery_chart_carries_the_power_status(self):
        ups().status_for = MagicMock(return_value={**self._ok_reading(), "ups_status": "OL"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(
            [BatteryStatus.BATTERY_STATUS_ONLINE],
            list(self._battery_chart(response).battery_statuses),
        )

    def test_battery_statuses_keep_the_reading_order_of_the_flags(self):
        ups().status_for = MagicMock(return_value={**self._ok_reading(), "ups_status": "OB LB DISCHRG"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(
            [
                BatteryStatus.BATTERY_STATUS_ONBATTERY,
                BatteryStatus.BATTERY_STATUS_LOWBATTERY,
                BatteryStatus.BATTERY_STATUS_DISCHARGE,
            ],
            list(self._battery_chart(response).battery_statuses),
        )

    def test_a_flag_without_a_matching_enum_value_is_not_a_status(self):
        ups().status_for = MagicMock(return_value={**self._ok_reading(), "ups_status": "OL CHRG"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(
            [BatteryStatus.BATTERY_STATUS_ONLINE],
            list(self._battery_chart(response).battery_statuses),
        )

    def test_flags_that_would_need_a_new_enum_value_are_logged(self):
        ups().status_for = MagicMock(return_value={**self._ok_reading(), "ups_status": "OL RB"})

        with self.assertLogs("crac_server.service.ups_service", level="WARNING") as logs:
            response = self.ups_service.GetStatus(None, None)

        self.assertEqual(
            [BatteryStatus.BATTERY_STATUS_ONLINE],
            list(self._battery_chart(response).battery_statuses),
        )
        self.assertIn("RB", "\n".join(logs.output))

    def test_battery_chart_has_no_statuses_when_the_metric_is_not_read(self):
        ups().status_for = MagicMock(return_value=self._ok_reading())

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(self._battery_chart(response).battery_statuses))

    def test_get_status_isolates_connection_error(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._ok_reading()

        ups().status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(2, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_isolates_generic_exception(self):
        def side_effect(device):
            if device == "apc-3000":
                raise KeyError("missing config")
            return self._ok_reading()

        ups().status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(2, len(response.charts))

    def test_get_status_all_devices_fail(self):
        ups().status_for = MagicMock(side_effect=ConnectionError("unreachable"))

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_skips_battery_chart_when_metric_unavailable(self):
        ups().status_for = MagicMock(return_value={"input_voltage": "220", "battery_charge": None})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.battery" not in urn for urn in urns))
        self.assertEqual(2, len(response.charts))

    def test_get_status_skips_voltage_chart_when_metric_unavailable(self):
        ups().status_for = MagicMock(return_value={"input_voltage": None, "battery_charge": "80"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.voltage" not in urn for urn in urns))
        self.assertEqual(2, len(response.charts))

    def test_get_status_skips_current_chart_when_metric_unavailable(self):
        ups().status_for = MagicMock(return_value={**self._ok_reading(), "output_current": None})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.current" not in urn for urn in urns))
        self.assertEqual(4, len(response.charts))

    def test_get_status_does_not_read_config_for_excluded_metric(self):
        ups().status_for = MagicMock(return_value=self._ok_reading())

        def missing_current_config(key, section="automazione"):
            if section == "output_current":
                raise KeyError(section)
            return getvalue_side_effect()(key, section)

        with patch("crac_server.service.ups_service.Config.getValue", side_effect=missing_current_config):
            response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.current" not in urn for urn in urns))
        self.assertEqual(4, len(response.charts))

    def test_get_status_reports_a_state_for_every_configured_device(self):
        ups().status_for = MagicMock(side_effect=lambda device: self._ok_reading())

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(
            [("apc-3000", UpsStatus.UPS_STATUS_NORMAL), ("cyberpower", UpsStatus.UPS_STATUS_NORMAL)],
            [(d.name, d.status) for d in response.device_states],
        )

    def test_get_status_keeps_an_unreadable_device_in_device_states(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._ok_reading()

        ups().status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(
            [("apc-3000", UpsStatus.UPS_STATUS_UNSPECIFIED), ("cyberpower", UpsStatus.UPS_STATUS_NORMAL)],
            [(d.name, d.status) for d in response.device_states],
        )

    def test_get_status_device_state_is_per_device_not_the_aggregate(self):
        def side_effect(device):
            if device == "apc-3000":
                return {**self._ok_reading(), "battery_charge": "10"}
            return self._ok_reading()

        ups().status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, response.status)
        self.assertEqual(
            [("apc-3000", UpsStatus.UPS_STATUS_DANGER), ("cyberpower", UpsStatus.UPS_STATUS_NORMAL)],
            [(d.name, d.status) for d in response.device_states],
        )

    def test_get_status_reports_unspecified_when_a_device_is_unreachable(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._ok_reading()

        ups().status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(2, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_does_not_mask_a_real_danger_with_unspecified(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return {**self._ok_reading(), "battery_charge": "10"}

        ups().status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, response.status)

    def test_get_status_isolates_non_numeric_value(self):
        def side_effect(device):
            if device == "apc-3000":
                return {**self._ok_reading(), "battery_charge": "N/A"}
            return self._ok_reading()

        ups().status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(2, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_does_not_emit_partial_charts_for_failing_device(self):
        ups().status_for = MagicMock(return_value={**self._ok_reading(), "battery_charge": "N/A"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))

    def test_get_status_all_devices_non_numeric(self):
        ups().status_for = MagicMock(return_value={**self._ok_reading(), "input_voltage": ""})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_device_present_with_no_charts_when_all_metrics_unavailable(self):
        ups().status_for = MagicMock(return_value={"input_voltage": None, "battery_charge": None, "output_current": None})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        self.assertEqual(0, len(response.charts))


class TestUpsServiceKeepsConfigurationErrorsVisible(unittest.TestCase):
    """A misconfigured threshold reported as an unreadable device hides a
    broken configuration behind a hardware problem."""

    def setUp(self):
        self._original_status_for = ups().status_for
        self._patches = [
            patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge"}),
            patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge"])),
            patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect("apc-3000")),
        ]
        for p in self._patches:
            p.start()
        self.ups_service = UpsService()

    def tearDown(self):
        ups().status_for = self._original_status_for
        for p in self._patches:
            p.stop()

    def test_reraises_a_broken_threshold_instead_of_blaming_the_device(self):
        ups().status_for = MagicMock(return_value={"battery_charge": "80"})

        def unreachable_band(key, section="automazione"):
            if section == "battery_charge" and key == "danger":
                return "50..35"
            return getvalue_side_effect("apc-3000")(key, section)

        with patch("crac_server.service.ups_service.Config.getValue", side_effect=unreachable_band):
            with self.assertRaises(ChartConfigError):
                self.ups_service.GetStatus(None, None)

    def test_still_reports_the_device_as_unreadable_when_the_reading_fails(self):
        ups().status_for = MagicMock(side_effect=ConnectionError("unreachable"))

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)


class TestUpsChartLevels(unittest.TestCase):
    """The level of a reading, from the device to the reported status."""

    def setUp(self):
        self._original_status_for = ups().status_for
        self._patches = [
            patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "input_voltage": "input.voltage"}),
            patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "input_voltage"])),
            patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect("apc-3000")),
        ]
        for p in self._patches:
            p.start()
        self.ups_service = UpsService()

    def tearDown(self):
        ups().status_for = self._original_status_for
        for p in self._patches:
            p.stop()

    def _chart_status(self, urn_suffix, **reading):
        ups().status_for = MagicMock(return_value={"battery_charge": "80", "input_voltage": "220", **reading})
        response = self.ups_service.GetStatus(None, None)
        chart = next(c.chart for c in response.charts if c.chart.urn.endswith(urn_suffix))
        return chart.status

    def _device_status(self, **reading):
        ups().status_for = MagicMock(return_value={"battery_charge": "80", "input_voltage": "220", **reading})
        return self.ups_service.GetStatus(None, None).device_states[0].status

    def test_battery_inside_each_band(self):
        self.assertEqual(ChartStatus.CHART_STATUS_NORMAL, self._chart_status("battery", battery_charge="80"))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._chart_status("battery", battery_charge="40"))
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, self._chart_status("battery", battery_charge="20"))

    def test_battery_on_a_threshold_takes_the_more_severe_level(self):
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, self._chart_status("battery", battery_charge="35"))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._chart_status("battery", battery_charge="50"))

    def test_voltage_is_warning_below_and_danger_above_the_safe_range(self):
        self.assertEqual(ChartStatus.CHART_STATUS_NORMAL, self._chart_status("voltage", input_voltage="220"))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._chart_status("voltage", input_voltage="200"))
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, self._chart_status("voltage", input_voltage="245"))

    def test_a_reading_past_the_scale_keeps_the_level_of_the_outermost_band(self):
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, self._chart_status("voltage", input_voltage="400"))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._chart_status("voltage", input_voltage="0"))

    def test_the_device_takes_the_level_of_its_worst_chart(self):
        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, self._device_status())
        self.assertEqual(UpsStatus.UPS_STATUS_WARNING, self._device_status(battery_charge="40"))
        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, self._device_status(input_voltage="245"))
        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, self._device_status(battery_charge="40", input_voltage="245"))
