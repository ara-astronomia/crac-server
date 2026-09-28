import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_protobuf.curtains_pb2 import CurtainStatus
from crac_protobuf.roof_pb2 import RoofAction, RoofRequest, RoofResponse, RoofStatus
from crac_protobuf.telescope_pb2 import TelescopeStatus
from crac_server.converter.roof_converter import RoofConverter, RoofMediator
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.handler.roof_handler import (
    RoofCurtainsHandler,
    RoofHandler,
    RoofTelescopeHandler,
    RoofWeatherHandler,
)


class TestRoofWeatherHandler(unittest.TestCase):
    """
    Opening the roof is refused on dangerous weather, and on unknown weather
    only when the installation asked for it.
    """

    def _handle(self, weather_status, block_on_unspecified):
        mediator = SimpleNamespace(status=RoofStatus.ROOF_CLOSED, action=RoofAction.OPEN, is_disabled=False)
        weather_response = WeatherResponse(status=weather_status)
        with (
            patch("crac_server.handler.roof_handler.Config.getRequiredBoolean", return_value=block_on_unspecified),
            patch.object(WeatherConverter, "convert", return_value=weather_response),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofWeatherHandler().handle(mediator)
        return mediator

    def test_disables_opening_on_dangerous_weather(self):
        mediator = self._handle(WeatherStatus.WEATHER_STATUS_DANGER, False)
        self.assertIs(True, mediator.is_disabled)

    def test_disables_opening_on_unknown_weather_when_configured_to_block(self):
        mediator = self._handle(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, True)
        self.assertIs(True, mediator.is_disabled)

    def test_allows_opening_on_unknown_weather_when_configured_not_to_block(self):
        mediator = self._handle(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, False)
        self.assertIs(False, mediator.is_disabled)


class TestRoofHandlersOnARoofInError(unittest.TestCase):
    """
    A roof in error has no known position, so each command is checked for
    the way it would move the roof: closing needs the telescope and the
    curtains out of the way, opening needs safe weather. A plain status
    request disables nothing, since it asks for no movement.
    """

    def _mediator(self, action, motor_on=False, sensors_inconsistent=False):
        roof_in_error = MagicMock()
        roof_in_error.get_status.return_value = RoofStatus.ROOF_ERROR
        roof_in_error.motor.value = int(motor_on)
        roof_in_error.sensors_inconsistent = sensors_inconsistent
        with patch("crac_server.converter.roof_converter.roof", return_value=roof_in_error):
            return RoofMediator(RoofRequest(action=action))

    def _weather_handler(self, action, weather_status, motor_on=False):
        mediator = self._mediator(action, motor_on)
        with (
            patch("crac_server.handler.roof_handler.Config.getRequiredBoolean", return_value=False),
            patch.object(WeatherConverter, "convert", return_value=WeatherResponse(status=weather_status)),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofWeatherHandler().handle(mediator)
        return mediator

    def _telescope_handler(self, action, telescope_status, motor_on=False):
        mediator = self._mediator(action, motor_on)
        parked_telescope = SimpleNamespace(status=telescope_status, polling=True)
        with (
            patch("crac_server.handler.roof_handler.telescope", return_value=parked_telescope),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofTelescopeHandler().handle(mediator)
        return mediator

    def _curtains_handler(self, action, curtain_status, motor_on=False):
        mediator = self._mediator(action, motor_on)
        curtain = SimpleNamespace(get_status=lambda: curtain_status)
        with (
            patch("crac_server.handler.roof_handler.curtain_east", return_value=curtain),
            patch("crac_server.handler.roof_handler.curtain_west", return_value=curtain),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofCurtainsHandler().handle(mediator)
        return mediator

    def test_opening_is_refused_on_dangerous_weather(self):
        mediator = self._weather_handler(RoofAction.OPEN, WeatherStatus.WEATHER_STATUS_DANGER)
        self.assertIs(True, mediator.is_disabled)

    def test_closing_is_allowed_on_dangerous_weather(self):
        mediator = self._weather_handler(RoofAction.CLOSE, WeatherStatus.WEATHER_STATUS_DANGER)
        self.assertIs(False, mediator.is_disabled)

    def test_closing_is_refused_with_the_telescope_not_secure(self):
        mediator = self._telescope_handler(RoofAction.CLOSE, TelescopeStatus.EAST)
        self.assertIs(True, mediator.is_disabled)

    def test_closing_is_allowed_with_the_telescope_secure(self):
        mediator = self._telescope_handler(RoofAction.CLOSE, TelescopeStatus.PARKED)
        self.assertIs(False, mediator.is_disabled)

    def test_opening_does_not_look_at_the_telescope(self):
        mediator = self._telescope_handler(RoofAction.OPEN, TelescopeStatus.EAST)
        self.assertIs(False, mediator.is_disabled)

    def test_closing_is_refused_with_the_curtains_out(self):
        mediator = self._curtains_handler(RoofAction.CLOSE, CurtainStatus.CURTAIN_OPENED)
        self.assertIs(True, mediator.is_disabled)

    def test_closing_is_allowed_with_the_curtains_in(self):
        mediator = self._curtains_handler(RoofAction.CLOSE, CurtainStatus.CURTAIN_DISABLED)
        self.assertIs(False, mediator.is_disabled)

    def test_a_status_request_with_the_motor_closing_checks_the_weather(self):
        mediator = self._weather_handler(RoofAction.CHECK_ROOF, WeatherStatus.WEATHER_STATUS_DANGER, motor_on=False)
        self.assertIs(True, mediator.is_disabled)

    def test_a_status_request_with_the_motor_closing_ignores_the_telescope(self):
        mediator = self._telescope_handler(RoofAction.CHECK_ROOF, TelescopeStatus.EAST, motor_on=False)
        self.assertIs(False, mediator.is_disabled)

    def test_a_status_request_with_the_motor_opening_checks_the_telescope(self):
        mediator = self._telescope_handler(RoofAction.CHECK_ROOF, TelescopeStatus.EAST, motor_on=True)
        self.assertIs(True, mediator.is_disabled)

    def test_a_status_request_with_the_motor_opening_checks_the_curtains(self):
        mediator = self._curtains_handler(RoofAction.CHECK_ROOF, CurtainStatus.CURTAIN_OPENED, motor_on=True)
        self.assertIs(True, mediator.is_disabled)

    def test_a_status_request_with_the_motor_opening_ignores_the_weather(self):
        mediator = self._weather_handler(RoofAction.CHECK_ROOF, WeatherStatus.WEATHER_STATUS_DANGER, motor_on=True)
        self.assertIs(False, mediator.is_disabled)

    def test_with_both_limit_switches_active_no_command_moves_the_roof(self):
        for action in (RoofAction.OPEN, RoofAction.CLOSE, RoofAction.CHECK_ROOF):
            with self.subTest(action=RoofAction.Name(action)):
                mediator = self._mediator(action, sensors_inconsistent=True)
                with patch.object(RoofConverter, "convert", return_value=RoofResponse()):
                    RoofHandler().handle(mediator)

                self.assertIs(True, mediator.is_disabled)
                mediator.button.open.assert_not_called()
                mediator.button.close.assert_not_called()

if __name__ == "__main__":
    unittest.main()
