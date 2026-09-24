from functools import lru_cache
from importlib.metadata import entry_points

from crac_server.component.telescope.telescope import Telescope
from crac_server.config import Config

TELESCOPE_DRIVERS_GROUP = "crac_server.telescope_drivers"


@lru_cache(maxsize=1)
def telescope() -> Telescope:
    driver = Config.getValue("driver", "telescope")
    drivers = entry_points(group=TELESCOPE_DRIVERS_GROUP)
    try:
        driver_class = drivers[driver].load()
    except KeyError:
        available = ", ".join(sorted(drivers.names)) or "none installed"
        raise ValueError(f"Unknown telescope driver '{driver}', available: {available}")
    return driver_class()
