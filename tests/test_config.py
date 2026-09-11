import configparser
import os
import tempfile
import unittest
from contextlib import contextmanager
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


class TestConfigIsReadOnceFromDisk(unittest.TestCase):
    """
    Every getter used to build a Config of its own, reparsing config.ini from
    disk: 54 reads for a single weather response. The file is parsed once and
    parsed again only when it changes, so editing it on a running server keeps
    taking effect without a restart.
    """

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "config.ini")
        self._write(interval="10")
        path_patch = patch("crac_server.config.CONFIG_PATH", self.path)
        path_patch.start()
        self.addCleanup(path_patch.stop)

    def _write(self, interval):
        with open(self.path, "w") as config_file:
            config_file.write(f"[roof_board]\nroof_timeout = {interval}\nswitch_roof = 4\ngpio_mock = on\n")

    @contextmanager
    def _counting_reads(self):
        reads = []
        real_read = configparser.ConfigParser.read

        def counted_read(parser, *args, **kwargs):
            reads.append(args)
            return real_read(parser, *args, **kwargs)

        with patch.object(configparser.ConfigParser, "read", counted_read):
            yield reads

    def test_many_keys_cost_a_single_parse(self):
        with self._counting_reads() as reads:
            for _ in range(20):
                Config.getInt("roof_timeout", "roof_board")
                Config.getValue("switch_roof", "roof_board")
                Config.getBoolean("gpio_mock", "roof_board")

        self.assertEqual(1, len(reads))

    def test_a_changed_file_is_parsed_again(self):
        self.assertEqual(10, Config.getInt("roof_timeout", "roof_board"))

        self._write(interval="50")
        stat = os.stat(self.path)
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        self.assertEqual(50, Config.getInt("roof_timeout", "roof_board"))

    def test_an_untouched_file_is_not_parsed_again(self):
        Config.getInt("roof_timeout", "roof_board")

        with self._counting_reads() as reads:
            Config.getInt("roof_timeout", "roof_board")

        self.assertEqual([], reads)
