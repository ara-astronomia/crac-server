import os
import unittest
from configparser import ConfigParser
from crac_server.component.ups.simulator.ups import Ups


class TestSimulatorUps(unittest.TestCase):

    def setUp(self):
        import crac_server.component.ups.simulator.ups as ups_module
        self.ups_path = os.path.join(os.path.dirname(ups_module.__file__), "ups.ini")
        self._had_file = os.path.exists(self.ups_path)
        if self._had_file:
            with open(self.ups_path) as f:
                self._original_content = f.read()
        self.ups = Ups(host="", port=3493, login="", password="", time_expired=60)

    def tearDown(self):
        if self._had_file:
            with open(self.ups_path, "w") as f:
                f.write(self._original_content)
        elif os.path.exists(self.ups_path):
            os.remove(self.ups_path)

    def test_read_returns_defaults_when_no_fail_flag(self):
        result = self.ups._read("apc-3000")
        self.assertEqual("OL", result["ups.status"])

    def test_read_includes_output_current(self):
        result = self.ups._read("apc-3000")
        self.assertIn("output.current", result)

    def test_read_reports_attributes_beyond_the_dynamic_ones(self):
        # simula un UPS NUT reale, che espone molti più attributi di quelli
        # letti oggi da [ups_metrics] - il filtro deve avvenire in
        # Ups.status_for(), non riducendo già qui cosa il device "ha"
        result = self.ups._read("apc-3000")
        self.assertGreater(len(result), 4)
        self.assertIn("driver.name", result)

    def test_read_raises_when_fail_flag_set(self):
        config = ConfigParser()
        config.read(self.ups_path)
        if not config.has_section("apc-3000"):
            config.add_section("apc-3000")
        config.set("apc-3000", "fail", "true")
        with open(self.ups_path, "w") as f:
            config.write(f)

        with self.assertRaises(ConnectionError):
            self.ups._read("apc-3000")
