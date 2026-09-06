import os
import unittest
from unittest.mock import MagicMock
from crac_protobuf.ups_pb2 import UpsStatus
from crac_server.component.ups import UPS
from crac_server.service.ups_service import UpsService


class TestUpsService(unittest.TestCase):

    def setUp(self):
        self.ups_service = UpsService()
        self._original_status_for = UPS.status_for

    def tearDown(self):
        UPS.status_for = self._original_status_for
        os.environ.pop("UPS_DISABLED_METRICS", None)

    def _ok_reading(self):
        return {"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": "3"}

    def test_get_status_all_devices_ok(self):
        UPS.status_for = MagicMock(side_effect=lambda device: self._ok_reading())

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        self.assertEqual(6, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, response.status)

    def test_get_status_isolates_connection_error(self):
        def side_effect(device):
            if device == "apc-3000":
                raise ConnectionError("unreachable")
            return self._ok_reading()

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(3, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, response.status)

    def test_get_status_isolates_generic_exception(self):
        def side_effect(device):
            if device == "apc-3000":
                raise KeyError("missing config")
            return self._ok_reading()

        UPS.status_for = MagicMock(side_effect=side_effect)

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["cyberpower"], list(response.devices))
        self.assertEqual(3, len(response.charts))

    def test_get_status_all_devices_fail(self):
        UPS.status_for = MagicMock(side_effect=ConnectionError("unreachable"))

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual([], list(response.devices))
        self.assertEqual(0, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_UNSPECIFIED, response.status)

    def test_get_status_skips_battery_chart_when_metric_unavailable(self):
        UPS.status_for = MagicMock(return_value={"input_voltage": "220", "battery_charge": None, "ups_status": "OL", "output_current": "3"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.battery" not in urn for urn in urns))
        self.assertEqual(4, len(response.charts))

    def test_get_status_skips_voltage_chart_when_metric_unavailable(self):
        UPS.status_for = MagicMock(return_value={"input_voltage": None, "battery_charge": "80", "ups_status": "OL", "output_current": "3"})

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.voltage" not in urn for urn in urns))
        self.assertEqual(4, len(response.charts))

    def test_get_status_skips_current_chart_when_metric_unavailable(self):
        UPS.status_for = MagicMock(return_value={"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": None})

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

    def test_get_status_respects_disabled_metrics_config(self):
        os.environ["UPS_DISABLED_METRICS"] = "ampere,battery"
        UPS.status_for = MagicMock(side_effect=lambda device: self._ok_reading())

        response = self.ups_service.GetStatus(None, None)

        urns = [chart.chart.urn for chart in response.charts]
        self.assertTrue(all("chart.current" not in urn and "chart.battery" not in urn for urn in urns))
        self.assertEqual(2, len(response.charts))
