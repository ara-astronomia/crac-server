import unittest
from unittest.mock import MagicMock, patch
from crac_server.component.ups.nut.ups import Ups


class TestNutUps(unittest.TestCase):

    def setUp(self):
        self.ups = Ups(host="localhost", login="crac", password="pw", time_expired=60)

    @patch("crac_server.component.ups.nut.ups.PyNUTClient")
    def test_status_for_reads_all_metrics(self, PyNUTClientMock):
        client = MagicMock()
        client.list_vars.return_value = {
            "input.voltage": "220.0",
            "battery.charge": "90",
            "ups.status": "OL",
            "output.current": "4.2",
        }
        PyNUTClientMock.return_value = client

        result = self.ups.status_for("apc-3000")

        self.assertEqual("220.0", result["input_voltage"])
        self.assertEqual("90", result["battery_charge"])
        self.assertEqual("OL", result["ups_status"])
        self.assertEqual("4.2", result["output_current"])

    @patch("crac_server.component.ups.nut.ups.PyNUTClient")
    def test_status_for_returns_none_for_unsupported_metrics(self, PyNUTClientMock):
        client = MagicMock()
        client.list_vars.return_value = {}
        PyNUTClientMock.return_value = client

        result = self.ups.status_for("apc-3000")

        self.assertIsNone(result["input_voltage"])
        self.assertIsNone(result["battery_charge"])
        self.assertIsNone(result["ups_status"])
        self.assertIsNone(result["output_current"])
