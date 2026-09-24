from functools import lru_cache
from importlib.metadata import entry_points

from crac_server.component.telescope.telescope import Telescope
from crac_server.config import Config

TELESCOPE_DRIVERS_GROUP = "crac_server.telescope_drivers"


@lru_cache(maxsize=1)
def telescope() -> Telescope:
    driver = Config.getValue("driver", "telescope")
    drivers = entry_points(group=TELESCOPE_DRIVERS_GROUP)
    matches = drivers.select(name=driver)
    if not matches:
        available = ", ".join(sorted(drivers.names)) or "none installed"
        raise ValueError(f"Unknown telescope driver '{driver}', available: {available}")
    if len(matches) > 1:
        packages = ", ".join(str(m.value) for m in matches)
        raise ValueError(f"Telescope driver '{driver}' is registered by more than one package: {packages}")
    return next(iter(matches)).load()()
