import unittest
from unittest.mock import patch
from crac_server.component.ups.ups import Ups

ALL_METRICS = {
    "battery_charge": "battery.charge",
    "input_voltage": "input.voltage",
    "output_current": "output.current",
    "ups_status": "ups.status",
}


class FakeUps(Ups):
    def __init__(self, raw):
        super().__init__(host="", login="", password="", time_expired=60)
        self._raw = raw

    def _read(self, device: str) -> dict[str, str]:
        return self._raw


class TestUps(unittest.TestCase):

    def _status_for(self, raw, metrics=ALL_METRICS):
        ups = FakeUps(raw)
        with patch("crac_server.component.ups.ups.Config.get_section", return_value=metrics):
            return ups.status_for("apc-3000")

    def test_status_for_returns_all_metrics_when_present(self):
        result = self._status_for({"input.voltage": "220", "battery.charge": "80", "ups.status": "OL", "output.current": "3"})

        self.assertEqual("220", result["input_voltage"])
        self.assertEqual("80", result["battery_charge"])
        self.assertEqual("OL", result["ups_status"])
        self.assertEqual("3", result["output_current"])

    def test_status_for_raises_when_configured_metric_missing(self):
        with self.assertRaises(Exception):
            self._status_for({"input.voltage": "220", "battery.charge": None, "ups.status": "OL", "output.current": "3"})

    def test_status_for_omits_metric_not_configured_even_if_missing(self):
        result = self._status_for(
            {"input.voltage": "220", "battery.charge": None, "ups.status": "OL", "output.current": "3"},
            metrics={"input_voltage": "input.voltage", "output_current": "output.current", "ups_status": "ups.status"},
        )

        self.assertNotIn("battery_charge", result)
        self.assertEqual("220", result["input_voltage"])

    def test_status_for_omits_metric_not_configured_even_if_present(self):
        result = self._status_for(
            {"input.voltage": "220", "battery.charge": "80", "ups.status": "OL", "output.current": "3"},
            metrics={"battery_charge": "battery.charge", "output_current": "output.current", "ups_status": "ups.status"},
        )

        self.assertNotIn("input_voltage", result)

    def test_status_for_omits_current_metric_not_configured(self):
        result = self._status_for(
            {"input.voltage": "220", "battery.charge": "80", "ups.status": "OL", "output.current": None},
            metrics={"battery_charge": "battery.charge", "input_voltage": "input.voltage", "ups_status": "ups.status"},
        )

        self.assertNotIn("output_current", result)

    def test_status_for_raises_when_ups_status_configured_but_missing(self):
        with self.assertRaises(Exception):
            self._status_for({"input.voltage": "220", "battery.charge": "80", "ups.status": None, "output.current": "3"})

    def test_status_for_omits_ups_status_when_not_configured(self):
        result = self._status_for(
            {"input.voltage": "220", "battery.charge": "80", "ups.status": None, "output.current": "3"},
            metrics={"battery_charge": "battery.charge", "input_voltage": "input.voltage", "output_current": "output.current"},
        )

        self.assertNotIn("ups_status", result)
