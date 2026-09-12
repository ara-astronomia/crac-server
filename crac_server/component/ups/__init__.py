import importlib
from functools import lru_cache

from crac_server.component.ups.ups import Ups
from crac_server.config import Config


@lru_cache(maxsize=1)
def ups() -> Ups:
    driver = Config.getValue("driver", "ups")
    return importlib.import_module(f"crac_server.component.ups.{driver}.ups").Ups(
        host=Config.getValue("hostname", "ups"),
        login=Config.getValue("login", "ups"),
        password=Config.getValue("password", "ups"),
        time_expired=Config.getInt("time_expired", "ups"),
    )
