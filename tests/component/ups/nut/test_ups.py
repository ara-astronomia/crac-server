import unittest
from unittest.mock import MagicMock, patch
from crac_server.component.ups.nut.ups import Ups


class TestNutUps(unittest.TestCase):

    def setUp(self):
        self.ups = Ups(host="localhost", login="crac", password="pw", time_expired=60)

    @patch("crac_server.component.ups.nut.ups.PyNUTClient")
    def test_status_for_includes_output_current(self, PyNUTClientMock):
        client = MagicMock()
        client.list_vars.return_value = {
            "input.voltage": "220.0",
            "battery.charge": "90",
            "ups.status": "OL",
            "output.current": "4.2",
        }
        PyNUTClientMock.return_value = client

        result = self.ups.status_for("apc-3000")

        self.assertEqual("4.2", result["output_current"])

    @patch("crac_server.component.ups.nut.ups.PyNUTClient")
    def test_status_for_output_current_none_when_unsupported(self, PyNUTClientMock):
        client = MagicMock()
        client.list_vars.return_value = {
            "input.voltage": "220.0",
            "battery.charge": "90",
            "ups.status": "OL",
        }
        PyNUTClientMock.return_value = client

        result = self.ups.status_for("apc-3000")

        self.assertIsNone(result["output_current"])
