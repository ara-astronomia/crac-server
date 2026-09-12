"""
Suite setup: mock GPIO and the configuration next to the tests, both in place
before any component gets imported.
"""

import os

os.environ["CRAC_CONFIG_PATH"] = os.path.join(os.path.dirname(__file__), "config.ini")

from gpiozero import Device  # noqa: E402
from gpiozero.pins.mock import MockFactory  # noqa: E402

if Device.pin_factory is not None:
    Device.pin_factory.reset()
Device.pin_factory = MockFactory()
