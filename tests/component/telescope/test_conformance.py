import os
import unittest

from crac_server.component.telescope.conformance import TelescopeConformanceTestCase
from crac_server.component.telescope.simulator.telescope import INI_PATH, Telescope as SimulatorTelescope


class TestSimulatorConformance(TelescopeConformanceTestCase, unittest.TestCase):
    """simulator is the reference driver: this doubles as an example of how
    a third-party connector proves it respects the Telescope contract."""

    def driver(self) -> SimulatorTelescope:
        return SimulatorTelescope()

    def tearDown(self):
        if os.path.exists(INI_PATH):
            os.remove(INI_PATH)


class TestConformanceRequiresTestCase(unittest.TestCase):

    def test_forgetting_unittest_testcase_raises_at_class_definition(self):
        with self.assertRaises(TypeError):
            class Forgetful(TelescopeConformanceTestCase):
                def driver(self):
                    return SimulatorTelescope()


if __name__ == "__main__":
    unittest.main()
