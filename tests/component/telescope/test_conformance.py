import os
import unittest

from crac_server.component.telescope.conformance import TelescopeConformanceTestCase
from crac_server.component.telescope.simulator import telescope as simulator_module
from crac_server.component.telescope.simulator.telescope import Telescope as SimulatorTelescope

INI_PATH = os.path.join(os.path.dirname(simulator_module.__file__), "telescope.ini")


class TestSimulatorConformance(TelescopeConformanceTestCase, unittest.TestCase):
    """simulator is the reference driver: this doubles as an example of how
    a third-party connector proves it respects the Telescope contract."""

    def driver(self) -> SimulatorTelescope:
        return SimulatorTelescope()

    def tearDown(self):
        if os.path.exists(INI_PATH):
            os.remove(INI_PATH)


if __name__ == "__main__":
    unittest.main()
