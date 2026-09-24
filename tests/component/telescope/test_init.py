import unittest
from importlib.metadata import EntryPoint, EntryPoints
from unittest.mock import patch

from crac_server.component.telescope import telescope
from crac_server.component.telescope.simulator.telescope import Telescope as SimulatorTelescope


class TestTelescopeFactory(unittest.TestCase):

    def setUp(self):
        telescope.cache_clear()

    def tearDown(self):
        telescope.cache_clear()

    def test_resolves_the_configured_driver_by_entry_point_name(self):
        with patch("crac_server.component.telescope.Config.getValue", return_value="simulator"):
            self.assertIsInstance(telescope(), SimulatorTelescope)

    def test_unknown_driver_raises_a_clear_error(self):
        with patch("crac_server.component.telescope.Config.getValue", return_value="does-not-exist"):
            with self.assertRaisesRegex(ValueError, "does-not-exist"):
                telescope()

    def test_two_packages_registering_the_same_name_raise_instead_of_picking_one(self):
        dup = EntryPoints([
            EntryPoint(name="dup", value="pkg_a.telescope:Telescope", group="crac_server.telescope_drivers"),
            EntryPoint(name="dup", value="pkg_b.telescope:Telescope", group="crac_server.telescope_drivers"),
        ])
        with patch("crac_server.component.telescope.Config.getValue", return_value="dup"), \
             patch("crac_server.component.telescope.entry_points", return_value=dup):
            with self.assertRaisesRegex(ValueError, "pkg_a.*pkg_b|pkg_b.*pkg_a"):
                telescope()
