from crac_server.component.roof.roof_control import RoofControl
from crac_server.component.roof.simulator.roof_pins import simulated_roof
from crac_server.config import Config


ROOF = simulated_roof() if Config.getBoolean("gpio_mock", "server") else RoofControl()
