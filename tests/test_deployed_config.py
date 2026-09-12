import configparser
import os
import unittest

import crac_server.config


class TestTheDeployedConfiguration(unittest.TestCase):
    """
    The committed config.ini is what runs in the dome when no environment
    override is in place: a mocked GPIO there drives nothing at all.
    """

    def test_the_gpio_is_the_real_one(self):
        parser = configparser.ConfigParser()
        parser.read(os.path.join(os.path.dirname(crac_server.config.__file__), "config.ini"))

        self.assertFalse(parser.getboolean("server", "gpio_mock"))
