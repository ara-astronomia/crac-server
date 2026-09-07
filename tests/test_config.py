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


class TestGetSectionKeys(unittest.TestCase):
    """
    get_section scarta le chiavi con valore vuoto: chi deve accorgersi di una
    chiave svuotata per sbaglio ha bisogno dei nomi non filtrati.
    """

    def test_returns_every_key_including_the_empty_ones(self):
        import configparser
        parser = configparser.ConfigParser()
        parser.read_string("[ups_metrics]\nbattery_charge = battery.charge\ninput_voltage =\n")
        with patch("crac_server.config.Config.__init__", lambda self: setattr(self, "configparser", parser)):
            self.assertEqual({"battery_charge", "input_voltage"}, set(Config.get_section_keys("ups_metrics")))
            self.assertEqual({"battery_charge"}, set(Config.get_section("ups_metrics")))


class TestGetRequiredBoolean(unittest.TestCase):
    """
    Safety switches must not be readable as "off" just because nobody wrote
    them down: an absent key has to fail loudly, the way a missing threshold
    does in getRequiredFloat.
    """

    def _get_required_boolean(self, raw_value):
        with patch("crac_server.config.Config.getValue", return_value=raw_value):
            return Config.getRequiredBoolean("block_on_unspecified", "weather")

    def test_returns_true_for_a_true_value(self):
        self.assertIs(True, self._get_required_boolean("true"))

    def test_returns_false_for_a_false_value(self):
        self.assertIs(False, self._get_required_boolean("false"))

    def test_raises_on_empty_value(self):
        with self.assertRaises(ValueError):
            self._get_required_boolean("")

    def test_raises_on_non_boolean_value(self):
        with self.assertRaises(ValueError):
            self._get_required_boolean("maybe")

    def test_propagates_error_when_key_or_section_is_missing(self):
        with patch("crac_server.config.Config.getValue", side_effect=KeyError("weather")):
            with self.assertRaises(KeyError):
                Config.getRequiredBoolean("block_on_unspecified", "weather")
