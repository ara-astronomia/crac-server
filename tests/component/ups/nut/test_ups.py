import unittest
from unittest.mock import MagicMock, patch
from crac_server.component.ups.nut.ups import Ups


class TestNutUps(unittest.TestCase):

    def setUp(self):
        self.ups = Ups(host="localhost", login="crac", password="pw", time_expired=60)

    @patch("crac_server.component.ups.nut.ups.PyNUTClient")
    def test_read_returns_raw_nut_vars_unchanged(self, PyNUTClientMock):
        client = MagicMock()
        client.list_vars.return_value = {
            "input.voltage": "220.0",
            "battery.charge": "90",
            "ups.status": "OL",
            "output.current": "4.2",
        }
        PyNUTClientMock.return_value = client

        result = self.ups._read("apc-3000")

        self.assertEqual(client.list_vars.return_value, result)

    @patch("crac_server.component.ups.nut.ups.PyNUTClient")
    def test_read_returns_whatever_nut_reports_even_if_incomplete(self, PyNUTClientMock):
        client = MagicMock()
        client.list_vars.return_value = {"input.voltage": "220.0"}
        PyNUTClientMock.return_value = client

        result = self.ups._read("apc-3000")

        self.assertEqual({"input.voltage": "220.0"}, result)
