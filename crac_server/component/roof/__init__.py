from crac_server.component.roof.roof_control import RoofControl
from crac_server.component.roof.simulator.roof_control import MockRoofControl
from crac_server.config import Config


ROOF = MockRoofControl() if Config.getBoolean("gpio_mock", "server") else RoofControl()
