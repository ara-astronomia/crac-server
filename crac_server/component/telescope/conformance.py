"""Reusable contract checks for a third-party Telescope driver: mix this
into your own unittest.TestCase and implement driver(). Checks only the
shape of the contract, with no compatibility promise across versions."""
from crac_protobuf.telescope_pb2 import TelescopeSpeed, TelescopeStatus
from crac_server.component.telescope.telescope import Telescope, TelescopeReading


class TelescopeConformanceTestCase:

    def driver(self) -> Telescope:
        raise NotImplementedError("override driver() to return your Telescope instance")

    def test_retrieve_returns_a_telescope_reading(self):
        reading = self.driver().retrieve()
        self.assertIsInstance(reading, TelescopeReading)
        self.assertIn(reading.speed, TelescopeSpeed.values())
        self.assertIn(reading.status, TelescopeStatus.values())

    def test_has_tracking_off_capability_is_a_bool(self):
        self.assertIsInstance(self.driver().has_tracking_off_capability, bool)

    def test_park_flat_set_speed_accept_every_telescope_speed(self):
        driver = self.driver()
        for method in (driver.set_speed, driver.park, driver.flat):
            for speed in TelescopeSpeed.values():
                with self.subTest(method=method.__name__, speed=speed):
                    method(speed)
