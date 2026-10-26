import asyncio
import unittest
from unittest.mock import MagicMock, patch
from crac_protobuf.chart_pb2 import ChartStatus
from crac_protobuf.emergency_closure_pb2 import (
    EmergencyClosure,  # type: ignore
    EmergencyClosureStatus,  # type: ignore
    EmergencyClosureTrigger,  # type: ignore
)
from crac_protobuf.ups_pb2 import BatteryStatus, UpsStatus
from crac_server.component.ups import ups
from crac_server.converter.chart_config import ChartConfigError
from crac_server.service.ups_service import UpsService, ups_service


UPS = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_UPS
UPS_UNAVAILABLE = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_UPS_UNAVAILABLE


SECTIONS = {
    "battery_charge": {"scale": "0..100", "warning": "35..50", "danger": "..35"},
    "input_voltage": {"scale": "0..250", "warning": "..209, 241.5.."},
    "output_current": {"scale": "0..20", "danger": "8.."},
    "ups_emergency": {
        "critical_time": "300",
        "critical_battery_percentage": "60",
        "block_on_unspecified": "true",
    },
    "ups": {"check_interval": "30"},
}


def getkeys_side_effect(enabled):
    def side_effect(name):
        if name == "ups_metrics":
            return enabled
        return list(SECTIONS[name])
    return side_effect


def getvalue_side_effect(ups_list="apc-3000,cyberpower", enabled_checks="battery_charge"):
    def side_effect(key, section="automazione"):
        if (key, section) == ("ups_list", "ups"):
            return ups_list
        if (key, section) == ("enabled_checks", "ups_emergency"):
            return enabled_checks
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

    def test_get_status_counts_a_device_without_an_enabled_reading_as_unknown(self):
        ups().status_for = MagicMock(return_value={"input_voltage": "220", "battery_charge": None})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)
        self.assertEqual(
            [UpsStatus.UPS_STATUS_UNSPECIFIED, UpsStatus.UPS_STATUS_UNSPECIFIED],
            [device.status for device in response.device_states],
        )

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

    def test_get_status_counts_a_device_without_charts_as_unknown(self):
        ups().status_for = MagicMock(return_value={"input_voltage": None, "battery_charge": None, "output_current": None})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)


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

    def test_voltage_is_a_warning_on_both_sides_of_the_safe_range(self):
        self.assertEqual(ChartStatus.CHART_STATUS_NORMAL, self._chart_status("voltage", input_voltage="220"))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._chart_status("voltage", input_voltage="200"))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._chart_status("voltage", input_voltage="245"))

    def test_a_reading_past_the_scale_keeps_the_level_of_the_outermost_band(self):
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._chart_status("voltage", input_voltage="400"))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._chart_status("voltage", input_voltage="0"))

    def test_the_device_takes_the_level_of_its_worst_chart(self):
        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, self._device_status())
        self.assertEqual(UpsStatus.UPS_STATUS_WARNING, self._device_status(battery_charge="40"))
        self.assertEqual(UpsStatus.UPS_STATUS_WARNING, self._device_status(input_voltage="245"))
        self.assertEqual(UpsStatus.UPS_STATUS_WARNING, self._device_status(battery_charge="40", input_voltage="245"))


class TestUpsEmergencyStartupValidation(unittest.TestCase):
    """The emergency configuration must stop the startup: a safety check
    that cannot run is worse than a server that refuses to start."""

    METRICS = {"battery_charge": "battery.charge", "ups_status": "ups.status"}

    def _build(self, getvalue):
        with patch("crac_server.service.ups_service.Config.get_section", return_value=self.METRICS), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "ups_status"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue):
            return UpsService()

    def test_a_check_that_the_server_does_not_read_cannot_be_enabled(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._build(getvalue_side_effect(enabled_checks="battery_charge,ups_status,output_current"))
        self.assertIn("output_current", str(ctx.exception))

    def test_an_unknown_check_name_fails_at_startup(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._build(getvalue_side_effect(enabled_checks="battery_charge,input_voltage"))
        self.assertIn("input_voltage", str(ctx.exception))

    def test_an_empty_whitelist_fails_at_startup(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._build(getvalue_side_effect(enabled_checks=""))
        self.assertIn("enabled_checks", str(ctx.exception))

    def test_a_missing_block_on_unspecified_fails_at_startup(self):
        def without_block_on_unspecified(key, section="automazione"):
            if (key, section) == ("block_on_unspecified", "ups_emergency"):
                return ""
            return getvalue_side_effect()(key, section)

        with self.assertRaises(ValueError) as ctx:
            self._build(without_block_on_unspecified)
        self.assertIn("block_on_unspecified", str(ctx.exception))

    def test_a_missing_critical_time_fails_at_startup(self):
        def without_critical_time(key, section="automazione"):
            if (key, section) == ("critical_time", "ups_emergency"):
                return ""
            return getvalue_side_effect()(key, section)

        with self.assertRaises(ValueError) as ctx:
            self._build(without_critical_time)
        self.assertIn("critical_time", str(ctx.exception))


class TestUpsCheckInterval(unittest.TestCase):

    def _build(self, check_interval):
        def getvalue(key, section="automazione"):
            if (key, section) == ("check_interval", "ups"):
                return check_interval
            return getvalue_side_effect()(key, section)

        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge"])), \
             patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue):
            return UpsService()

    def test_a_missing_check_interval_fails_at_startup(self):
        with patch("crac_server.service.ups_service.Config.getRequiredFloat", side_effect=KeyError("check_interval")):
            with self.assertRaises(KeyError):
                self._build("30")

    def test_an_interval_below_30_seconds_fails_at_startup(self):
        with self.assertRaises(ValueError) as ctx:
            self._build("29")
        self.assertIn("check_interval", str(ctx.exception))

    def test_30_seconds_is_accepted(self):
        self.assertEqual(30, self._build("30").check_interval)


class TestUpsServiceCheck(unittest.IsolatedAsyncioTestCase):
    """The emergency reaction runs in the watch, on the event loop: any
    single device in a critical condition is enough to report."""

    def setUp(self):
        self._original_status_for = ups().status_for
        self._patches = [
            patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "input_voltage": "input.voltage", "ups_status": "ups.status"}),
            patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "input_voltage", "ups_status"])),
            patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()),
            patch("crac_server.service.ups_service.emergency_closure"),
            patch("crac_server.service.ups_service.ups_emergency"),
            patch("crac_server.service.external_conditions.external_conditions"),
        ]
        mocks = [p.start() for p in self._patches]
        self.addCleanup(self._restore)
        self.closure = mocks[3].return_value
        self.closure.state.return_value = EmergencyClosure()
        self.ups_emergency = mocks[4].return_value
        self.conditions = mocks[5].return_value
        self.ups_service = UpsService()
        self.ups_emergency.device_is_critical.return_value = False
        self.ups_emergency.can_be_judged.return_value = True

    def _restore(self):
        ups().status_for = self._original_status_for
        for p in self._patches:
            p.stop()

    async def _check(self):
        with patch("crac_server.service.ups_service.emergency_closure") as closure:
            closure.return_value.state.return_value = EmergencyClosure(
                status=EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_IN_PROGRESS,
            )
            response = await self.ups_service.check()
        return response, closure.return_value

    def _reading(self, device):
        return {"battery_charge": "80", "input_voltage": "220", "ups_status": "OL"}

    async def test_a_critical_device_is_reported_to_the_closure(self):
        ups().status_for = MagicMock(side_effect=self._reading)
        self.ups_emergency.device_is_critical.return_value = True

        response, closure = await self._check()

        closure.report.assert_called_once_with(UPS, True)

    async def test_no_critical_device_with_all_readable_settles_the_closure(self):
        ups().status_for = MagicMock(side_effect=self._reading)

        response, closure = await self._check()

        closure.report.assert_called_once_with(UPS, False)

    async def test_one_device_in_threshold_is_enough(self):
        ups().status_for = MagicMock(side_effect=self._reading)
        self.ups_emergency.device_is_critical.side_effect = lambda device, *args: device == "apc-3000"

        response, closure = await self._check()

        closure.report.assert_called_once_with(UPS, True)

    async def test_an_unreadable_device_reports_nothing(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._reading(device)

        ups().status_for = MagicMock(side_effect=side_effect)

        response, closure = await self._check()

        closure.report.assert_not_called()
        self.ups_emergency.device_lost.assert_called_once_with("apc-3000")
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    async def test_an_unreadable_device_does_not_hide_a_real_danger(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._reading(device)

        ups().status_for = MagicMock(side_effect=side_effect)
        self.ups_emergency.device_is_critical.side_effect = lambda device, *args: device == "cyberpower"

        response, closure = await self._check()

        closure.report.assert_called_once_with(UPS, True)

    async def test_two_critical_checks_report_once_each(self):
        ups().status_for = MagicMock(side_effect=self._reading)
        self.ups_emergency.device_is_critical.return_value = True

        _, first = await self._check()
        _, second = await self._check()

        first.report.assert_called_once_with(UPS, True)
        second.report.assert_called_once_with(UPS, True)

    async def test_a_device_that_cannot_be_judged_counts_like_an_unreadable_one(self):
        ups().status_for = MagicMock(side_effect=self._reading)
        self.ups_emergency.can_be_judged.side_effect = lambda device, *args: device != "apc-3000"

        response, closure = await self._check()

        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)
        self.ups_emergency.device_lost.assert_called_once_with("apc-3000")
        closure.report.assert_not_called()

    async def test_a_device_that_cannot_be_judged_does_not_hide_the_others(self):
        ups().status_for = MagicMock(side_effect=self._reading)
        self.ups_emergency.can_be_judged.side_effect = lambda device, *args: device != "apc-3000"
        self.ups_emergency.device_is_critical.side_effect = lambda device, *args: device == "cyberpower"

        response, closure = await self._check()

        closure.report.assert_called_once_with(UPS, True)

    async def test_a_blind_reading_does_not_hide_a_real_danger_of_the_other_device(self):
        self._patches[4].stop()
        self._patches.pop(4)
        readings = {
            "apc-3000": {"ups_status": "OL", "input_voltage": "220"},
            "cyberpower": {"battery_charge": "10", "ups_status": "OL", "input_voltage": "220"},
        }
        ups().status_for = MagicMock(side_effect=lambda device: readings[device])

        response, closure = await self._check()

        closure.report.assert_called_once_with(UPS, True)
        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, response.status)

    async def test_every_response_carries_the_closure_state(self):
        ups().status_for = MagicMock(side_effect=self._reading)

        response, closure = await self._check()

        self.assertEqual(closure.state.return_value, response.emergency_closure)

    async def test_a_check_with_all_devices_readable_tells_the_conditions_the_ups_is_available(self):
        ups().status_for = MagicMock(side_effect=self._reading)

        await self.ups_service.check()

        self.conditions.note_availability.assert_called_once_with(UPS_UNAVAILABLE, True)

    async def test_an_unreadable_device_tells_the_conditions_the_ups_is_not_available(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._reading(device)

        ups().status_for = MagicMock(side_effect=side_effect)

        await self.ups_service.check()

        self.conditions.note_availability.assert_called_once_with(UPS_UNAVAILABLE, False)


class TestUpsServiceWatchesOnItsOwn(unittest.IsolatedAsyncioTestCase):
    """The safety decision must not depend on a client polling GetStatus:
    the service checks the UPS by itself, on the event loop."""

    SERVICE_LOGGER = "crac_server.service.ups_service"

    def setUp(self):
        self._original_status_for = ups().status_for
        patches = [
            patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "ups_status": "ups.status"}),
            patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "ups_status"])),
            patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()),
            patch("crac_server.service.ups_service.emergency_closure"),
            patch("crac_server.service.ups_service.ups_emergency"),
            patch("crac_server.service.external_conditions.external_conditions"),
        ]
        mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.addCleanup(self._restore_status_for)
        self.closure = mocks[3].return_value
        self.closure.state.return_value = EmergencyClosure()
        self.ups_emergency = mocks[4].return_value
        self.service = UpsService()
        self.service.check_interval = 0.01
        self.ups_emergency.device_is_critical.return_value = True
        ups().status_for = MagicMock(side_effect=lambda device: {"battery_charge": "80", "ups_status": "OL"})

    def _restore_status_for(self):
        ups().status_for = self._original_status_for

    async def test_a_critical_ups_is_reported_without_any_client(self):
        await self.__watch_until_checked(times=1)

        self.closure.report.assert_called_with(UPS, True)

    async def test_a_failed_check_is_logged_and_the_watch_goes_on(self):
        statuses = iter([RuntimeError("battery_charge not reported"), True, True])
        self.ups_emergency.device_is_critical.side_effect = lambda *args: next(statuses)

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__watch_until_checked(times=2)

        self.assertTrue(any("RuntimeError" in record.getMessage() for record in captured.records))
        self.closure.report.assert_called_with(UPS, True)

    async def test_an_unreadable_device_is_logged_and_reports_nothing(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return {"battery_charge": "80", "ups_status": "OL"}

        ups().status_for = MagicMock(side_effect=side_effect)
        self.ups_emergency.device_is_critical.return_value = False

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__watch_until_checked(times=1)

        self.assertTrue(any("apc-3000" in record.getMessage() for record in captured.records))
        self.closure.report.assert_not_called()

    async def test_the_watch_says_when_it_starts_and_how_often_it_checks(self):
        with self.assertLogs(self.SERVICE_LOGGER, level="INFO") as captured:
            await self.__watch_until_checked(times=1)

        self.assertIn(str(self.service.check_interval), captured.records[0].getMessage())

    async def test_the_watch_waits_check_interval_between_two_checks(self):
        with patch("crac_server.service.ups_service.asyncio.sleep", side_effect=asyncio.CancelledError) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await self.service.watch()

        sleep.assert_awaited_once_with(self.service.check_interval)

    async def __watch_until_checked(self, times):
        """Run the watch until the given number of checks is over, which is
        when the next one starts reading."""
        task = asyncio.create_task(self.service.watch())
        try:
            async with asyncio.timeout(2):
                while ups().status_for.call_count < times * len(self.service._configured_devices()):
                    await asyncio.sleep(0.001)
        finally:
            task.cancel()


class TestTheCachedStatus(unittest.IsolatedAsyncioTestCase):
    """What a command can ask without waiting for the UPS to answer:
    the status of the last check, unknown until one has run."""

    def setUp(self):
        ups_service.cache_clear()
        self.addCleanup(ups_service.cache_clear)
        self._original_status_for = ups().status_for
        self._patches = [
            patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "ups_status": "ups.status"}),
            patch("crac_server.service.ups_service.Config.get_section_keys", side_effect=getkeys_side_effect(["battery_charge", "ups_status"])),
            patch("crac_server.service.ups_service.Config.getValue", side_effect=getvalue_side_effect()),
            patch("crac_server.service.ups_service.emergency_closure"),
            patch("crac_server.service.ups_service.ups_emergency"),
            patch("crac_server.service.external_conditions.external_conditions"),
        ]
        mocks = [p.start() for p in self._patches]
        self.addCleanup(self._restore)
        self.closure = mocks[3].return_value
        self.closure.state.return_value = EmergencyClosure()
        self.emergency = mocks[4].return_value
        self.emergency.device_is_critical.return_value = False
        self.emergency.can_be_judged.return_value = True
        ups_service()

    def _restore(self):
        ups().status_for = self._original_status_for
        for p in self._patches:
            p.stop()

    async def test_before_the_first_check_the_status_is_unknown(self):
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, ups_service().cached_status())

    async def test_the_cached_status_is_the_one_of_the_last_check(self):
        ups().status_for = MagicMock(side_effect=lambda device: {"battery_charge": "10", "ups_status": "OL"})

        with patch("crac_server.service.ups_service.emergency_closure") as closure:
            closure.return_value.state.return_value = EmergencyClosure()
            await ups_service().check()

        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, ups_service().cached_status())


class TestTheClosureConditionIsADangerToo(TestUpsServiceCheck):
    """Whatever makes the closure start is a danger for the operator and
    for the gate: the charts alone would call it healthy."""

    async def test_a_critical_check_marks_the_whole_response_as_danger(self):
        ups().status_for = MagicMock(side_effect=self._reading)
        self.ups_emergency.device_is_critical.return_value = True

        response, _ = await self._check()

        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, response.status)

    async def test_the_display_read_keeps_the_danger_of_the_last_check(self):
        ups().status_for = MagicMock(side_effect=self._reading)
        self.ups_emergency.device_is_critical.return_value = True
        await self.ups_service.check()

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, response.status)

    async def test_the_display_read_drops_the_danger_when_the_check_says_healthy(self):
        ups().status_for = MagicMock(side_effect=self._reading)
        self.ups_emergency.device_is_critical.return_value = False
        await self.ups_service.check()

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, response.status)
