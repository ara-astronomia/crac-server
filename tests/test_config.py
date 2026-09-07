import unittest
from unittest.mock import patch
from crac_server.config import Config


class TestGetRequiredFloat(unittest.TestCase):

    def _get_required_float(self, raw_value):
        with patch("crac_server.config.Config.getValue", return_value=raw_value):
            return Config.getRequiredFloat("lower_bound", "battery_charge.ok")

    def test_returns_float_for_a_numeric_value(self):
        self.assertEqual(50.0, self._get_required_float("50"))

    def test_returns_zero_for_an_explicit_zero(self):
        # "0" è un valore legittimo, non un valore mancante
        self.assertEqual(0.0, self._get_required_float("0"))

    def test_raises_on_empty_value(self):
        # getFloat qui tornerebbe 0 in silenzio, falsificando la soglia
        with self.assertRaises(ValueError):
            self._get_required_float("")

    def test_raises_on_non_numeric_value(self):
        with self.assertRaises(ValueError):
            self._get_required_float("abc")

    def test_propagates_error_when_key_or_section_is_missing(self):
        with patch("crac_server.config.Config.getValue", side_effect=KeyError("battery_charge.ok")):
            with self.assertRaises(KeyError):
                Config.getRequiredFloat("lower_bound", "battery_charge.ok")
