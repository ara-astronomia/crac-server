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


class TestUpsService(unittest.TestCase):

    def setUp(self):
        self.ups_service = UpsService()
        self._original_status_for = UPS.status_for
        self._getfloat_patch = patch("crac_server.service.ups_service.Config.getFloat", side_effect=getfloat_side_effect)
        self._getvalue_patch = patch("crac_server.service.ups_service.Config.getValue", return_value="apc-3000,cyberpower")
        self._getfloat_patch.start()
        self._getvalue_patch.start()

    def tearDown(self):
        UPS.status_for = self._original_status_for
        self._getfloat_patch.stop()
        self._getvalue_patch.stop()

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
        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, response.status)

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

        with patch("crac_server.service.ups_service.Config.getFloat", side_effect=missing_current_config):
            response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.current" not in urn for urn in urns))
        self.assertEqual(4, len(response.charts))

    def test_get_status_device_present_with_no_charts_when_all_metrics_unavailable(self):
        UPS.status_for = MagicMock(return_value={"input_voltage": None, "battery_charge": None, "ups_status": None, "output_current": None})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        self.assertEqual(0, len(response.charts))
