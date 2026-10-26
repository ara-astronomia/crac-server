import unittest
from unittest.mock import MagicMock, call, patch

from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_protobuf.emergency_closure_pb2 import EmergencyClosureTrigger
from crac_protobuf.roof_pb2 import RoofStatus
from crac_protobuf.ups_pb2 import UpsStatus
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.service.external_conditions import ExternalConditions
from crac_server.service.ups_service import UpsService, ups_service


WEATHER_UNAVAILABLE = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER_UNAVAILABLE
UPS_UNAVAILABLE = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_UPS_UNAVAILABLE
MODULE = "crac_server.service.external_conditions"
WAIT = 300.0
UPS_WAIT = 600.0


class TestOperationBlocked(unittest.TestCase):
    """One answer to whether the world outside the dome lets the observatory
    operate: the components ask here instead of reading the weather each in
    its own way."""

    def _blocked(self, weather_status, block_on_unspecified):
        conditions = ExternalConditions()
        with (
            patch(f"{MODULE}.Config.getRequiredBoolean", return_value=block_on_unspecified) as block_config,
            patch.object(WeatherConverter, "convert", return_value=WeatherResponse(status=weather_status)),
            patch(f"{MODULE}.ups_service") as ups_service,
        ):
            ups_service.return_value.cached_status.return_value = UpsStatus.UPS_STATUS_NORMAL
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


class TestOperationBlockedByTheUps(unittest.TestCase):

    def _blocked(self, ups_status, block_on_unspecified):
        conditions = ExternalConditions()
        with (
            patch.object(WeatherConverter, "convert", return_value=WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL)),
            patch(f"{MODULE}.Config.getRequiredBoolean", return_value=block_on_unspecified) as block_config,
            patch(f"{MODULE}.ups_service") as ups_service,
        ):
            ups_service.return_value.cached_status.return_value = ups_status
            blocked = conditions.operation_blocked()

        return blocked, block_config

    def test_a_dangerous_ups_blocks_the_operation(self):
        blocked, _ = self._blocked(UpsStatus.UPS_STATUS_DANGER, False)

        self.assertIs(True, blocked)

    def test_an_unknown_ups_blocks_the_operation_only_when_configured_to_block(self):
        for block_on_unspecified, expected in ((True, True), (False, False)):
            with self.subTest(block_on_unspecified=block_on_unspecified):
                blocked, block_config = self._blocked(UpsStatus.UPS_STATUS_UNSPECIFIED, block_on_unspecified)

                self.assertIs(expected, blocked)
                block_config.assert_called_once_with("block_on_unspecified", "ups_emergency")

    def test_an_ups_out_of_danger_does_not_block_the_operation(self):
        for status in (UpsStatus.UPS_STATUS_NORMAL, UpsStatus.UPS_STATUS_WARNING):
            with self.subTest(status=UpsStatus.Name(status)):
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


class TestTheMissingUpsClosesTheOpenObservatory(unittest.TestCase):

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
        wait_patcher = patch(f"{MODULE}.Config.getRequiredFloat", return_value=UPS_WAIT)
        self.wait_config = wait_patcher.start()
        self.addCleanup(wait_patcher.stop)

    def _note(self, available):
        self.conditions.note_availability(UPS_UNAVAILABLE, available)

    def test_the_closure_starts_once_the_wait_is_over(self):
        self._note(False)
        self.clock += UPS_WAIT
        self._note(False)

        self.closure.report.assert_called_once_with(UPS_UNAVAILABLE, True)
        self.wait_config.assert_called_with("close_on_unspecified_after", "ups_emergency")

    def test_a_reading_that_comes_back_settles_the_closure_it_had_started(self):
        self._note(False)
        self.clock += UPS_WAIT
        self._note(False)
        self._note(True)

        self.closure.report.assert_has_calls([
            call(UPS_UNAVAILABLE, True),
            call(UPS_UNAVAILABLE, False),
        ])


if __name__ == "__main__":
    unittest.main()


class TestTheGateNeverRaises(unittest.TestCase):
    """A gate that crashes takes the button away with an error: one that
    cannot judge says unknown, and blocks when configured to."""

    def _blocked(self, weather_error=None, ups_error=None):
        conditions = ExternalConditions()
        with (
            patch.object(WeatherConverter, "convert") as convert,
            patch(f"{MODULE}.Config.getRequiredBoolean", return_value=True),
            patch(f"{MODULE}.ups_service") as ups_service,
        ):
            convert.return_value = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL)
            if weather_error is not None:
                convert.side_effect = weather_error
            ups_service.return_value.cached_status.return_value = UpsStatus.UPS_STATUS_NORMAL
            if ups_error is not None:
                ups_service.return_value.cached_status.side_effect = ups_error
            return conditions.operation_blocked()

    def test_a_weather_that_cannot_be_read_blocks_instead_of_raising(self):
        self.assertIs(True, self._blocked(weather_error=KeyError("windSpeed")))

    def test_an_ups_that_cannot_be_read_blocks_instead_of_raising(self):
        self.assertIs(True, self._blocked(ups_error=RuntimeError("broken configuration")))


class TestTheGateNeverReadsTheUpsLive(unittest.TestCase):
    """The commands must not wait for the UPS to answer: the gate asks
    the last check of the watch, never the network."""

    def test_the_gate_does_not_call_the_live_read(self):
        ups_service.cache_clear()
        self.addCleanup(ups_service.cache_clear)
        conditions = ExternalConditions()
        with (
            patch.object(WeatherConverter, "convert", return_value=WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL)),
            patch(f"{MODULE}.Config.getRequiredBoolean", return_value=True),
            patch.object(UpsService, "GetStatus", side_effect=AssertionError("the gate read the UPS live")),
        ):
            blocked = conditions.operation_blocked()

        self.assertIs(True, blocked)
