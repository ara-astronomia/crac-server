import os
import unittest
from configparser import ConfigParser

from crac_protobuf.telescope_pb2 import TelescopeSpeed, TelescopeStatus
from crac_server.component.telescope.simulator import telescope as simulator_module
from crac_server.component.telescope.simulator.telescope import Telescope

INI_PATH = os.path.join(os.path.dirname(simulator_module.__file__), "telescope.ini")


class TestSimulatorTelescope(unittest.TestCase):
    """telescope.ini is the driver's own state file, not a mock - tests read
    it back and restore its original content instead of stubbing I/O."""

    def setUp(self):
        # None means the driver hadn't written it yet - a fresh checkout
        # doesn't ship this gitignored state file.
        self._original_ini = None
        if os.path.exists(INI_PATH):
            with open(INI_PATH) as f:
                self._original_ini = f.read()
        self.telescope = Telescope()

    def tearDown(self):
        if self._original_ini is None:
            if os.path.exists(INI_PATH):
                os.remove(INI_PATH)
        else:
            with open(INI_PATH, "w") as f:
                f.write(self._original_ini)

    def _read_coords(self):
        config = ConfigParser()
        config.read(INI_PATH)
        return config["coords"]

    def test_park_writes_configured_park_position(self):
        self.telescope.park(TelescopeSpeed.SPEED_NOT_TRACKING)
        coords = self._read_coords()
        self.assertEqual(coords["alt"], "1.0")
        self.assertEqual(coords["az"], "359.0")
        self.assertEqual((coords["tr"], coords["sl"]), ("1", "1"))

    def test_flat_writes_configured_flat_position(self):
        self.telescope.flat(TelescopeSpeed.SPEED_TRACKING)
        coords = self._read_coords()
        self.assertEqual(coords["alt"], "1.5")
        self.assertEqual(coords["az"], "358.5")
        self.assertEqual((coords["tr"], coords["sl"]), ("0", "1"))

    def test_set_speed_preserves_current_position(self):
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        self.telescope.set_speed(TelescopeSpeed.SPEED_SLEWING)
        coords = self._read_coords()
        self.assertEqual(coords["alt"], "1.0")
        self.assertEqual(coords["az"], "359.0")
        self.assertEqual((coords["tr"], coords["sl"]), ("1", "0"))

    def test_retrieve_speed_mapping(self):
        cases = [
            (TelescopeSpeed.SPEED_TRACKING, TelescopeSpeed.SPEED_TRACKING),
            (TelescopeSpeed.SPEED_SLEWING, TelescopeSpeed.SPEED_SLEWING),
            (TelescopeSpeed.SPEED_NOT_TRACKING, TelescopeSpeed.SPEED_NOT_TRACKING),
        ]
        for written, expected in cases:
            with self.subTest(written=written):
                self.telescope.set_speed(written)
                self.assertEqual(self.telescope._retrieve_speed(), expected)

    def test_retrieve_reads_back_the_written_state(self):
        self.telescope._polling = True
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        eq_coords, aa_coords, speed, status = self.telescope.retrieve()
        self.assertEqual((aa_coords.alt, aa_coords.az), (1.0, 359.0))
        self.assertIsNotNone(eq_coords)
        self.assertEqual(speed, TelescopeSpeed.SPEED_TRACKING)
        self.assertEqual(status, TelescopeStatus.PARKED)
