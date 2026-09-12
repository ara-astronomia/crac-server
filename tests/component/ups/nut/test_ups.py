import unittest
from unittest.mock import MagicMock, patch
from crac_server.component.ups.nut.ups import Ups


class TestNutUps(unittest.TestCase):

    def setUp(self):
        self.ups = Ups(host="localhost", port=3493, login="crac", password="pw", time_expired=60)

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


class TestNutUpsConnection(unittest.TestCase):
    """
    NUT does not always listen on 3493: the port configured for it has to reach
    the client, or changing it in config.ini does nothing at all.
    """

    @patch("crac_server.component.ups.nut.ups.PyNUTClient")
    def test_the_configured_port_reaches_the_client(self, PyNUTClientMock):
        Ups(host="localhost", port=3999, login="crac", password="pw", time_expired=60)._read("apc-3000")

        self.assertEqual(3999, PyNUTClientMock.call_args.kwargs["port"])
