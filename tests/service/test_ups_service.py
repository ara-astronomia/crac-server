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

    def _ok_reading(self):
        return {"input_voltage": "220", "battery_charge": "80", "ups_status": "OL"}

    def test_get_status_all_devices_ok(self):
        UPS.status_for = MagicMock(side_effect=lambda device: self._ok_reading())

        response = self.ups_service.GetStatus(None, None)

        self.assertEqual(["apc-3000", "cyberpower"], list(response.devices))
        self.assertEqual(4, len(response.charts))
        self.assertEqual(UpsStatus.UPS_STATUS_NORMAL, response.status)

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
