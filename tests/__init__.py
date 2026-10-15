"""Suite setup: the gpiozero mock and the configuration next to the tests, in
place before any component gets built. The reservation lock is reentrant: a
device collected while another reserves its pins closes itself under that lock."""

import os
from threading import RLock

os.environ["CRAC_CONFIG_PATH"] = os.path.join(os.path.dirname(__file__), "config.ini")

from gpiozero import Device  # noqa: E402
from gpiozero.pins.mock import MockFactory  # noqa: E402

if Device.pin_factory is not None:
    Device.pin_factory.reset()
Device.pin_factory = MockFactory()
Device.pin_factory._res_lock = RLock()
