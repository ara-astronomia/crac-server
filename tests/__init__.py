"""
Test suite setup, run before any test module is imported.

Two things get replaced here, both because the components reach for them while
being imported and a test has no chance to do it later: the GPIO pin factory,
which becomes the gpiozero mock, and the configuration file, which becomes the
one living next to the tests instead of the deployed config.ini.
"""

import os

os.environ["CRAC_CONFIG_PATH"] = os.path.join(os.path.dirname(__file__), "config.ini")

from gpiozero import Device  # noqa: E402
from gpiozero.pins.mock import MockFactory  # noqa: E402

if Device.pin_factory is not None:
    Device.pin_factory.reset()
Device.pin_factory = MockFactory()
