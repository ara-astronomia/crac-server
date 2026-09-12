import configparser
import os
import unittest

import crac_server.config


REPOSITORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestTheDeployedConfiguration(unittest.TestCase):
    """
    The committed config.ini is what runs in the dome when no environment
    override is in place: a mocked GPIO there drives nothing at all.
    """

    def test_the_gpio_is_the_real_one(self):
        parser = configparser.ConfigParser()
        parser.read(os.path.join(os.path.dirname(crac_server.config.__file__), "config.ini"))

        self.assertFalse(parser.getboolean("server", "gpio_mock"))

    def test_the_observing_site_is_not_written_to_the_mount(self):
        """
        A real mount keeps its own site and computes every RA/DEC <-> ALT/AZ
        conversion from it: what the dome runs must leave it alone.
        """
        parser = configparser.ConfigParser()
        parser.read(os.path.join(os.path.dirname(crac_server.config.__file__), "config.ini"))

        self.assertFalse(parser.getboolean("telescope", "sync_geographic_coordinates"))

    def test_the_environment_example_does_not_write_the_observing_site(self):
        with open(os.path.join(REPOSITORY, ".env.example")) as example:
            enabled = [
                line for line in example
                if line.strip().startswith("TELESCOPE_SYNC_GEOGRAPHIC_COORDINATES=")
            ]

        self.assertEqual([], enabled)

    def test_the_environment_example_does_not_enable_the_fake_gpio(self):
        """
        .env.example is meant to be copied into .env, in production as well:
        an enabled mock in there would reach the observatory.
        """
        with open(os.path.join(REPOSITORY, ".env.example")) as example:
            enabled = [
                line for line in example
                if line.strip().startswith("SERVER_GPIO_MOCK=")
            ]

        self.assertEqual([], enabled)
