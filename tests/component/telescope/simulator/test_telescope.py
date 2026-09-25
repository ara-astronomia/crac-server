import os
import unittest
from configparser import ConfigParser

from crac_protobuf.telescope_pb2 import AltazimutalCoords, TelescopeSpeed, TelescopeStatus
from crac_server.component.telescope.simulator.telescope import INI_PATH, Telescope


class TestSimulatorTelescope(unittest.TestCase):
    """telescope.ini is the driver's own scratch state, gitignored and
    rewritten whole on every command - tests just clean it up afterward."""

    def setUp(self):
        self.telescope = Telescope()

    def tearDown(self):
        if os.path.exists(INI_PATH):
            os.remove(INI_PATH)

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

    def test_retrieve_speed_is_error_on_an_unmapped_state(self):
        config = ConfigParser()
        config["coords"] = {"alt": "0", "az": "0", "tr": "0", "sl": "0", "error": "0"}
        with open(INI_PATH, "w") as f:
            config.write(f)
        self.assertEqual(self.telescope._retrieve_speed(), TelescopeSpeed.SPEED_ERROR)

    def test_retrieve_status_at_the_southwest_boundary_is_not_none(self):
        self.telescope._polling = True
        status = self.telescope._retrieve_status(AltazimutalCoords(alt=50, az=190))
        self.assertEqual(status, TelescopeStatus.WEST)

    def test_retrieve_reads_back_the_written_state(self):
        self.telescope._polling = True
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        eq_coords, aa_coords, speed, status = self.telescope.retrieve()
        self.assertEqual((aa_coords.alt, aa_coords.az), (1.0, 359.0))
        self.assertIsNotNone(eq_coords)
        self.assertEqual(speed, TelescopeSpeed.SPEED_TRACKING)
        self.assertEqual(status, TelescopeStatus.PARKED)
