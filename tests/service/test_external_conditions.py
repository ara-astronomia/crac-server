import unittest
from unittest.mock import MagicMock, call, patch

from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_protobuf.emergency_closure_pb2 import EmergencyClosureTrigger
from crac_protobuf.roof_pb2 import RoofStatus
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.service.external_conditions import ExternalConditions


WEATHER_UNAVAILABLE = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER_UNAVAILABLE
MODULE = "crac_server.service.external_conditions"
WAIT = 300.0


class TestOperationBlocked(unittest.TestCase):
    """One answer to whether the world outside the dome lets the observatory
    operate: the components ask here instead of reading the weather each in
    its own way."""

    def _blocked(self, weather_status, block_on_unspecified):
        conditions = ExternalConditions()
        with (
            patch(f"{MODULE}.Config.getRequiredBoolean", return_value=block_on_unspecified) as block_config,
            patch.object(WeatherConverter, "convert", return_value=WeatherResponse(status=weather_status)),
        ):
            blocked = conditions.operation_blocked()

        return blocked, block_config

    def test_dangerous_weather_blocks_the_operation(self):
        blocked, _ = self._blocked(WeatherStatus.WEATHER_STATUS_DANGER, False)

        self.assertIs(True, blocked)

    def test_unknown_weather_blocks_the_operation_only_when_configured_to_block(self):
        for block_on_unspecified, expected in ((True, True), (False, False)):
            with self.subTest(block_on_unspecified=block_on_unspecified):
                blocked, block_config = self._blocked(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, block_on_unspecified)

                self.assertIs(expected, blocked)
                block_config.assert_called_once_with("block_on_unspecified", "weather")

    def test_a_weather_out_of_danger_does_not_block_the_operation(self):
        for status in (WeatherStatus.WEATHER_STATUS_NORMAL, WeatherStatus.WEATHER_STATUS_WARNING):
            with self.subTest(status=WeatherStatus.Name(status)):
                blocked, _ = self._blocked(status, True)

                self.assertIs(False, blocked)


class TestTheMissingWeatherClosesTheOpenObservatory(unittest.TestCase):

    def setUp(self):
        self.conditions = ExternalConditions()
        self.clock = 1000.0
        self.roof = MagicMock()
        self.roof.get_status.return_value = RoofStatus.ROOF_OPENED
        self.closure = MagicMock()
        patchers = (
            patch(f"{MODULE}.monotonic", side_effect=lambda: self.clock),
            patch(f"{MODULE}.roof", return_value=self.roof),
            patch(f"{MODULE}.emergency_closure", return_value=self.closure),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        wait_patcher = patch(f"{MODULE}.Config.getRequiredFloat", return_value=WAIT)
        self.wait_config = wait_patcher.start()
        self.addCleanup(wait_patcher.stop)

    def _note(self, available):
        self.conditions.note_availability(WEATHER_UNAVAILABLE, available)

    def test_no_closure_before_the_wait_is_over(self):
        self._note(False)
        self.clock += WAIT - 1
        self._note(False)

        self.closure.report.assert_not_called()

    def test_the_closure_starts_once_the_wait_is_over(self):
        self._note(False)
        self.clock += WAIT
        self._note(False)

        self.closure.report.assert_called_once_with(WEATHER_UNAVAILABLE, True)
        self.wait_config.assert_called_with("close_on_unspecified_after", "weather")

    def test_every_check_keeps_reporting_the_critical_while_the_data_stays_missing(self):
        self._note(False)
        self.clock += WAIT
        self._note(False)
        self._note(False)

        self.assertEqual(2, self.closure.report.call_count)

    def test_a_reading_that_comes_back_restarts_the_wait(self):
        self._note(False)
        self.clock += WAIT - 100
        self._note(False)
        self._note(True)
        self.clock += 100
        self._note(False)

        self.closure.report.assert_called_once_with(WEATHER_UNAVAILABLE, False)

    def test_the_restarted_wait_runs_for_the_full_time_again(self):
        self._note(False)
        self.clock += WAIT - 100
        self._note(True)
        self.clock += WAIT + 100
        self._note(False)

        self.closure.report.assert_called_once_with(WEATHER_UNAVAILABLE, False)

    def test_a_reading_that_comes_back_settles_the_closure_it_had_started(self):
        self._note(False)
        self.clock += WAIT
        self._note(False)
        self._note(True)

        self.closure.report.assert_has_calls([
            call(WEATHER_UNAVAILABLE, True),
            call(WEATHER_UNAVAILABLE, False),
        ])

    def test_the_wait_does_not_advance_with_the_roof_closed(self):
        self._note(False)
        self.roof.get_status.return_value = RoofStatus.ROOF_CLOSED
        self.clock += WAIT + 50
        self._note(False)

        self.closure.report.assert_not_called()

    def test_reopening_the_roof_restarts_the_wait(self):
        self._note(False)
        self.roof.get_status.return_value = RoofStatus.ROOF_CLOSED
        self.clock += WAIT + 50
        self._note(False)
        self.roof.get_status.return_value = RoofStatus.ROOF_OPENED
        self._note(False)
        self.clock += WAIT
        self._note(False)

        self.closure.report.assert_called_once_with(WEATHER_UNAVAILABLE, True)


if __name__ == "__main__":
    unittest.main()
