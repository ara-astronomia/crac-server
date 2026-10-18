"""Suite setup: the gpiozero mock, the test configuration and the offline
IERS tables, in place before any component gets built. The reservation lock
is reentrant: a device collected while another reserves its pins closes under it."""

import os
from threading import RLock

os.environ["CRAC_CONFIG_PATH"] = os.path.join(os.path.dirname(__file__), "config.ini")

from astropy.utils.iers import conf as iers_conf  # noqa: E402
from gpiozero import Device  # noqa: E402
from gpiozero.pins.mock import MockFactory  # noqa: E402

iers_conf.auto_download = False
iers_conf.auto_max_age = None

if Device.pin_factory is not None:
    Device.pin_factory.reset()
Device.pin_factory = MockFactory()
Device.pin_factory._res_lock = RLock()
