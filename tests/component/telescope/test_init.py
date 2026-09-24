import unittest
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
