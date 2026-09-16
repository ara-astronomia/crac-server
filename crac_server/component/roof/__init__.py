from functools import lru_cache

from crac_server.component.roof.roof_control import RoofControl
from crac_server.component.roof.simulator.roof_pins import simulated_roof
from crac_server.config import Config


@lru_cache(maxsize=1)
def roof() -> RoofControl:
    return simulated_roof() if Config.getBoolean("gpio_mock", "server") else RoofControl()
