import importlib
from functools import lru_cache

from crac_server.component.telescope.telescope import Telescope
from crac_server.config import Config


@lru_cache(maxsize=1)
def telescope() -> Telescope:
    driver = Config.getValue("driver", "telescope")
    return importlib.import_module(f"crac_server.component.telescope.{driver}.telescope").Telescope()
