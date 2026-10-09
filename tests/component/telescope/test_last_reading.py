from contextlib import nullcontext
import math
import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.telescope_pb2 import (
    AltazimutalCoords,
    EquatorialCoords,
    TelescopeSpeed,
    TelescopeStatus,
)
from crac_server.component.telescope.telescope import Telescope, TelescopeReading


class ScriptedTelescope(Telescope):
    """Answers retrieve() with what the test queues, then stops the polling."""

    def __init__(self, *readings):
        super().__init__()
        self.readings = list(readings)

    def set_speed(self, speed):
        pass

    def park(self, speed):
        pass

    def flat(self, speed):
        pass

    def retrieve(self):
        reading = self.readings.pop(0)
        if not self.readings:
            self._polling = False
        if isinstance(reading, Exception):
            raise reading
        return reading


READING = TelescopeReading(
    EquatorialCoords(ra=1, dec=2), AltazimutalCoords(alt=5, az=180),
    TelescopeSpeed.SPEED_TRACKING, TelescopeStatus.SECURE,
)


class TestTelescopeLastReading(unittest.TestCase):

    def setUp(self):
        patcher = patch("crac_server.component.telescope.telescope.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_never_read_is_infinitely_old(self):
        self.assertEqual(math.inf, ScriptedTelescope().seconds_since_last_reading())

    def test_a_successful_reading_is_recent(self):
        telescope = ScriptedTelescope(READING, READING)
        self.__poll(telescope, last_reading_kept=True)

        self.assertLess(telescope.seconds_since_last_reading(), 1)

    def test_a_failed_reading_does_not_count(self):
        telescope = ScriptedTelescope(RuntimeError("mount gone"))
        self.__poll(telescope, last_reading_kept=True)

        self.assertEqual(math.inf, telescope.seconds_since_last_reading())

    def test_stopping_the_polling_forgets_the_last_reading(self):
        telescope = ScriptedTelescope(READING)
        self.__poll(telescope, last_reading_kept=False)

        self.assertEqual(math.inf, telescope.seconds_since_last_reading())

    def __poll(self, telescope, last_reading_kept):
        """Run the polling loop in this thread; with last_reading_kept the
        final reset is skipped, as for a loop still running."""
        telescope._polling = True
        with patch.object(telescope, "_reset", MagicMock()) if last_reading_kept else nullcontext():
            telescope._Telescope__read()

