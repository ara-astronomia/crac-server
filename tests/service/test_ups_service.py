import unittest
from unittest.mock import MagicMock, patch
from crac_protobuf.ups_pb2 import UpsStatus
from crac_server.component.ups import UPS
from crac_server.service.ups_service import UpsService


THRESHOLDS = {
    "battery_charge.ok": {"upper_bound": 100.0, "lower_bound": 50.0},
    "battery_charge.warning": {"upper_bound": 50.0, "lower_bound": 35.0},
    "battery_charge.danger": {"upper_bound": 35.0, "lower_bound": 0.0},
    "input_voltage.ok": {"upper_bound": 241.5, "lower_bound": 209.0},
    "input_voltage.danger_upper": {"upper_bound": 250.0, "lower_bound": 241.5},
    "input_voltage.danger_lower": {"upper_bound": 209.0, "lower_bound": 0.0},
    "output_current.ok": {"upper_bound": 8.0, "lower_bound": 0.0},
    "output_current.danger": {"upper_bound": 20.0, "lower_bound": 8.0},
}


def getfloat_side_effect(key, section):
    return THRESHOLDS[section][key]


class TestUpsServiceStartupValidation(unittest.TestCase):
    """La config delle soglie va validata all'avvio, non ad ogni poll."""

    def test_init_raises_when_an_enabled_metric_has_a_broken_threshold(self):
        def broken(key, section):
            if section.startswith("battery_charge"):
                raise ValueError(f"{section}.{key} non impostata in config.ini")
            return getfloat_side_effect(key, section)

        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", return_value=["battery_charge"]), \
             patch("crac_server.service.ups_service.Config.getRequiredFloat", side_effect=broken):
            with self.assertRaises(ValueError):
                UpsService()

    def test_init_raises_on_a_metric_the_service_cannot_chart(self):
        # una metrica sconosciuta non produce alcun chart, ma rende comunque
        # obbligatoria la sua presenza sul device: danno netto, va rifiutata
        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "battery_voltage": "battery.voltage"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", return_value=["battery_charge", "battery_voltage"]), \
             patch("crac_server.service.ups_service.Config.getRequiredFloat", side_effect=getfloat_side_effect):
            with self.assertRaises(RuntimeError) as ctx:
                UpsService()
        self.assertIn("battery_voltage", str(ctx.exception))

    def test_init_accepts_ups_status_even_without_a_chart(self):
        # ups_status e' letto di proposito senza produrre un chart: serve a #22
        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "ups_status": "ups.status"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", return_value=["battery_charge", "ups_status"]), \
             patch("crac_server.service.ups_service.Config.getRequiredFloat", side_effect=getfloat_side_effect):
            UpsService()

    def test_init_raises_on_a_metric_left_empty(self):
        # get_section scarta le chiavi vuote: senza questo controllo una
        # metrica svuotata per sbaglio smette di essere letta in silenzio
        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", return_value=["battery_charge", "input_voltage"]), \
             patch("crac_server.service.ups_service.Config.getRequiredFloat", side_effect=getfloat_side_effect):
            with self.assertRaises(RuntimeError) as ctx:
                UpsService()
        self.assertIn("input_voltage", str(ctx.exception))

    def test_init_ignores_thresholds_of_metrics_not_enabled(self):
        def missing_current_config(key, section):
            if section.startswith("output_current"):
                raise KeyError(section)
            return getfloat_side_effect(key, section)

        with patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "input_voltage": "input.voltage"}), \
             patch("crac_server.service.ups_service.Config.get_section_keys", return_value=["battery_charge", "input_voltage"]), \
             patch("crac_server.service.ups_service.Config.getRequiredFloat", side_effect=missing_current_config):
            UpsService()  # non deve sollevare: output_current non e' abilitata


class TestUpsService(unittest.TestCase):

    def setUp(self):
        self._original_status_for = UPS.status_for
        self._getfloat_patch = patch("crac_server.service.ups_service.Config.getRequiredFloat", side_effect=getfloat_side_effect)
        self._getvalue_patch = patch("crac_server.service.ups_service.Config.getValue", return_value="apc-3000,cyberpower")
        self._getsection_patch = patch("crac_server.service.ups_service.Config.get_section", return_value={"battery_charge": "battery.charge", "input_voltage": "input.voltage", "ups_status": "ups.status"})
        self._getkeys_patch = patch("crac_server.service.ups_service.Config.get_section_keys", return_value=["battery_charge", "input_voltage", "ups_status"])
        self._getfloat_patch.start()
        self._getvalue_patch.start()
        self._getsection_patch.start()
        self._getkeys_patch.start()
        self.ups_service = UpsService()

    def tearDown(self):
        UPS.status_for = self._original_status_for
        self._getfloat_patch.stop()
        self._getvalue_patch.stop()
        self._getsection_patch.stop()
        self._getkeys_patch.stop()

    def _ok_reading(self):
        return {"input_voltage": "220", "battery_charge": "80", "ups_status": "OL"}

    def test_get_status_all_devices_ok(self):
        UPS.status_for = MagicMock(side_effect=lambda device: self._ok_reading())

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        self.assertEqual(4, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, response.status)

    def test_get_status_builds_current_chart_when_present(self):
        UPS.status_for = MagicMock(return_value={**self._ok_reading(), "output_current": "3"})

        response = self.ups_service.GetStatus(None, None)

        urns = [chart.chart.urn for chart in response.charts]
        self.assertIn("ups.apc-3000.chart.current", urns)
        self.assertEqual(6, len(response.charts))

    def test_get_status_isolates_connection_error(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._ok_reading()

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(2, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_isolates_generic_exception(self):
        def side_effect(device):
            if device == "apc-3000":
                raise KeyError("missing config")
            return self._ok_reading()

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(2, len(response.charts))

    def test_get_status_all_devices_fail(self):
        UPS.status_for = MagicMock(side_effect=ConnectionError("unreachable"))

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_skips_battery_chart_when_metric_unavailable(self):
        UPS.status_for = MagicMock(return_value={"input_voltage": "220", "battery_charge": None, "ups_status": "OL"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.battery" not in urn for urn in urns))
        self.assertEqual(2, len(response.charts))

    def test_get_status_skips_voltage_chart_when_metric_unavailable(self):
        UPS.status_for = MagicMock(return_value={"input_voltage": None, "battery_charge": "80", "ups_status": "OL"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.voltage" not in urn for urn in urns))
        self.assertEqual(2, len(response.charts))

    def test_get_status_skips_current_chart_when_metric_unavailable(self):
        UPS.status_for = MagicMock(return_value={**self._ok_reading(), "output_current": None})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.current" not in urn for urn in urns))
        self.assertEqual(4, len(response.charts))

    def test_get_status_does_not_read_config_for_excluded_metric(self):
        UPS.status_for = MagicMock(return_value=self._ok_reading())

        def missing_current_config(key, section):
            if section.startswith("output_current"):
                raise KeyError(section)
            return getfloat_side_effect(key, section)

        with patch("crac_server.service.ups_service.Config.getRequiredFloat", side_effect=missing_current_config):
            response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.current" not in urn for urn in urns))
        self.assertEqual(4, len(response.charts))

    def test_get_status_reports_a_state_for_every_configured_device(self):
        UPS.status_for = MagicMock(side_effect=lambda device: self._ok_reading())

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(
            [("apc-3000", UpsStatus.UPS_STATUS_NORMAL), ("cyberpower", UpsStatus.UPS_STATUS_NORMAL)],
            [(d.name, d.status) for d in response.device_states],
        )

    def test_get_status_keeps_an_unreadable_device_in_device_states(self):
        # a differenza di "devices", un device muto non deve sparire: resta
        # elencato come esplicitamente ignoto
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._ok_reading()

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(
            [("apc-3000", UpsStatus.UPS_STATUS_UNSPECIFIED), ("cyberpower", UpsStatus.UPS_STATUS_NORMAL)],
            [(d.name, d.status) for d in response.device_states],
        )

    def test_get_status_device_state_is_per_device_not_the_aggregate(self):
        # l'aggregato e' DANGER per colpa di apc-3000, ma cyberpower sta bene:
        # il dettaglio per device non deve essere appiattito
        def side_effect(device):
            if device == "apc-3000":
                return {**self._ok_reading(), "battery_charge": "10"}
            return self._ok_reading()

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, response.status)
        self.assertEqual(
            [("apc-3000", UpsStatus.UPS_STATUS_DANGER), ("cyberpower", UpsStatus.UPS_STATUS_NORMAL)],
            [(d.name, d.status) for d in response.device_states],
        )

    def test_get_status_reports_unspecified_when_a_device_is_unreachable(self):
        # un UPS morto non deve poter essere spacciato per NORMAL solo perche'
        # l'altro sta bene: sul device perso non sappiamo nulla
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._ok_reading()

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(2, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_does_not_mask_a_real_danger_with_unspecified(self):
        # un device perso non deve declassare un pericolo reale rilevato
        # sull'altro: DANGER vince su "non so"
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return {**self._ok_reading(), "battery_charge": "10"}

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(UpsStatus.UPS_STATUS_DANGER, response.status)

    def test_get_status_isolates_non_numeric_value(self):
        def side_effect(device):
            if device == "apc-3000":
                return {**self._ok_reading(), "battery_charge": "N/A"}
            return self._ok_reading()

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(2, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_does_not_emit_partial_charts_for_failing_device(self):
        # tensione valida, batteria sporca: il device non deve finire nella
        # risposta a metà (un chart sì e uno no)
        UPS.status_for = MagicMock(return_value={**self._ok_reading(), "battery_charge": "N/A"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))

    def test_get_status_all_devices_non_numeric(self):
        UPS.status_for = MagicMock(return_value={**self._ok_reading(), "input_voltage": ""})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_device_present_with_no_charts_when_all_metrics_unavailable(self):
        UPS.status_for = MagicMock(return_value={"input_voltage": None, "battery_charge": None, "ups_status": None, "output_current": None})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        self.assertEqual(0, len(response.charts))
