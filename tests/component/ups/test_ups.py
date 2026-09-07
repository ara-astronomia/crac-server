import unittest
from unittest.mock import patch
from crac_server.component.ups.ups import Ups


class FakeUps(Ups):
    def __init__(self, raw):
        super().__init__(host="", login="", password="", time_expired=60)
        self._raw = raw

    def _read(self, device: str) -> dict[str, str]:
        return self._raw


class TestUps(unittest.TestCase):

    def _status_for(self, raw, disabled_metrics=""):
        ups = FakeUps(raw)
        with patch("crac_server.component.ups.ups.Config.getValue", return_value=disabled_metrics):
            return ups.status_for("apc-3000")

    def test_status_for_returns_all_metrics_when_present(self):
        result = self._status_for({"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": "3"})

        self.assertEqual("220", result["input_voltage"])
        self.assertEqual("80", result["battery_charge"])
        self.assertEqual("OL", result["ups_status"])
        self.assertEqual("3", result["output_current"])

    def test_status_for_raises_when_non_excluded_metric_missing(self):
        with self.assertRaises(Exception):
            self._status_for({"input_voltage": "220", "battery_charge": None, "ups_status": "OL", "output_current": "3"})

    def test_status_for_omits_excluded_metric_even_if_missing(self):
        result = self._status_for(
            {"input_voltage": "220", "battery_charge": None, "ups_status": "OL", "output_current": "3"},
            disabled_metrics="battery_charge",
        )

        self.assertNotIn("battery_charge", result)
        self.assertEqual("220", result["input_voltage"])

    def test_status_for_omits_excluded_metric_even_if_present(self):
        result = self._status_for(
            {"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": "3"},
            disabled_metrics="input_voltage",
        )

        self.assertNotIn("input_voltage", result)

    def test_status_for_omits_excluded_current_metric(self):
        result = self._status_for(
            {"input_voltage": "220", "battery_charge": "80", "ups_status": "OL", "output_current": None},
            disabled_metrics="output_current",
        )

        self.assertNotIn("output_current", result)

    def test_status_for_ups_status_is_never_gated_by_disabled_metrics(self):
        result = self._status_for({"input_voltage": "220", "battery_charge": "80", "ups_status": None, "output_current": "3"})

        self.assertIsNone(result["ups_status"])
