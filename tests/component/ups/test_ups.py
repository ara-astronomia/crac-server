import unittest
from unittest.mock import patch
from crac_server.component.ups.ups import Ups

ALL_METRICS = "battery_charge,input_voltage,output_current,ups_status"


class FakeUps(Ups):
    def __init__(self, raw):
        super().__init__(host="", login="", password="", time_expired=60)
        self._raw = raw

    def _read(self, device: str) -> dict[str, str]:
        return self._raw


class TestUps(unittest.TestCase):

    def _status_for(self, raw, enabled_metrics=ALL_METRICS):
        ups = FakeUps(raw)
        with patch("crac_server.component.ups.ups.Config.getValue", return_value=enabled_metrics):
            return ups.status_for("apc-3000")

    def test_status_for_returns_all_metrics_when_present(self):
        result = self._status_for({"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": "3"})

        self.assertEqual("220", result["input_voltage"])
        self.assertEqual("80", result["battery_charge"])
        self.assertEqual("OL", result["ups_status"])
        self.assertEqual("3", result["output_current"])

    def test_status_for_raises_when_enabled_metric_missing(self):
        with self.assertRaises(Exception):
            self._status_for({"input_voltage": "220", "battery_charge": None, "ups_status": "OL", "output_current": "3"})

    def test_status_for_omits_metric_not_in_whitelist_even_if_missing(self):
        result = self._status_for(
            {"input_voltage": "220", "battery_charge": None, "ups_status": "OL", "output_current": "3"},
            enabled_metrics="input_voltage,output_current,ups_status",
        )

        self.assertNotIn("battery_charge", result)
        self.assertEqual("220", result["input_voltage"])

    def test_status_for_omits_metric_not_in_whitelist_even_if_present(self):
        result = self._status_for(
            {"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": "3"},
            enabled_metrics="battery_charge,output_current,ups_status",
        )

        self.assertNotIn("input_voltage", result)

    def test_status_for_omits_current_metric_not_in_whitelist(self):
        result = self._status_for(
            {"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": None},
            enabled_metrics="battery_charge,input_voltage,ups_status",
        )

        self.assertNotIn("output_current", result)

    def test_status_for_raises_when_ups_status_whitelisted_but_missing(self):
        with self.assertRaises(Exception):
            self._status_for({"input_voltage": "220", "battery_charge": "80", "ups_status": None, "output_current": "3"})

    def test_status_for_omits_ups_status_when_not_whitelisted(self):
        result = self._status_for(
            {"input_voltage": "220", "battery_charge": "80", "ups_status": None, "output_current": "3"},
            enabled_metrics="battery_charge,input_voltage,output_current",
        )

        self.assertNotIn("ups_status", result)

    def test_status_for_raises_on_unknown_metric_in_whitelist(self):
        with self.assertRaises(Exception):
            self._status_for(
                {"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": "3"},
                enabled_metrics="battery_charge,totally_unknown_metric",
            )
