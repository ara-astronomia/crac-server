"""Reusable contract checks for a third-party Telescope driver: mix this
into your own unittest.TestCase and implement driver(). Checks only the
shape of the contract, with no compatibility promise across versions."""
import unittest

from crac_protobuf.telescope_pb2 import TelescopeSpeed, TelescopeStatus
from crac_server.component.telescope.telescope import Telescope, TelescopeReading


class TelescopeConformanceTestCase:

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not issubclass(cls, unittest.TestCase):
            raise TypeError(f"{cls.__name__} must also inherit unittest.TestCase")

    def driver(self) -> Telescope:
        raise NotImplementedError("override driver() to return your Telescope instance")

    def test_retrieve_returns_a_telescope_reading(self):
        reading = self.driver().retrieve()
        self.assertIsInstance(reading, TelescopeReading)
        self.assertIn(reading.speed, TelescopeSpeed.values())
        self.assertIn(reading.status, TelescopeStatus.values())

    def test_has_tracking_off_capability_is_a_bool(self):
        self.assertIsInstance(self.driver().has_tracking_off_capability, bool)

    def test_park_flat_set_speed_accept_every_commandable_speed(self):
        """SPEED_ERROR/SPEED_CENTERING are status-only values retrieve() can
        report, never commands a caller sends - callers only ever pass one
        of these three."""
        driver = self.driver()
        commandable_speeds = (TelescopeSpeed.SPEED_TRACKING, TelescopeSpeed.SPEED_NOT_TRACKING, TelescopeSpeed.SPEED_SLEWING)
        for method in (driver.set_speed, driver.park, driver.flat):
            for speed in commandable_speeds:
                with self.subTest(method=method.__name__, speed=speed):
                    method(speed)
