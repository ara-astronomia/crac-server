import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_protobuf.curtains_pb2 import CurtainsAction, CurtainsResponse, CurtainStatus
from crac_protobuf.telescope_pb2 import TelescopeSpeed, TelescopeStatus
from crac_server.converter.curtains_converter import CurtainsConverter
from crac_server.converter.weather_converter import WeatherConverter
from crac_protobuf.roof_pb2 import RoofStatus
from crac_server.handler.curtains_handler import (
    CurtainsDisableHandler,
    CurtainsMoveHandler,
    CurtainsRoofHandler,
    CurtainsWeatherHandler,
)


class TestCurtainsWeatherHandler(unittest.TestCase):
    """
    Enabling the curtains is refused on dangerous weather, and on unknown
    weather only when the installation asked for it.
    """

    def _handle(self, weather_status, block_on_unspecified):
        mediator = SimpleNamespace(
            status_east=CurtainStatus.CURTAIN_DISABLED,
            status_west=CurtainStatus.CURTAIN_DISABLED,
            action=CurtainsAction.ENABLE,
            is_disabled=False,
        )
        weather_response = WeatherResponse(status=weather_status)
        with (
            patch("crac_server.handler.curtains_handler.Config.getRequiredBoolean", return_value=block_on_unspecified),
            patch.object(WeatherConverter, "convert", return_value=weather_response),
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            CurtainsWeatherHandler().handle(mediator)
        return mediator

    def test_disables_the_curtains_on_dangerous_weather(self):
        mediator = self._handle(WeatherStatus.WEATHER_STATUS_DANGER, False)
        self.assertIs(True, mediator.is_disabled)

    def test_disables_the_curtains_on_unknown_weather_when_configured_to_block(self):
        mediator = self._handle(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, True)
        self.assertIs(True, mediator.is_disabled)

    def test_allows_the_curtains_on_unknown_weather_when_configured_not_to_block(self):
        mediator = self._handle(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, False)
        self.assertIs(False, mediator.is_disabled)


class TestCurtainsDisableHandler(unittest.TestCase):
    """DISABLE brings each curtain down whatever it is doing, powering its
    motor: the operator asked for it and is watching."""

    def _disable(self, status_east, status_west):
        east, west = MagicMock(), MagicMock()
        mediator = SimpleNamespace(
            action=CurtainsAction.DISABLE,
            status_east=status_east,
            status_west=status_west,
            button_east=east,
            button_west=west,
        )
        with patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()):
            CurtainsDisableHandler().handle(mediator)
        return east, west

    def test_a_moving_curtain_does_not_stop_the_other_from_being_disabled(self):
        east, west = self._disable(CurtainStatus.CURTAIN_OPENED, CurtainStatus.CURTAIN_OPENING)

        east.disable.assert_called_once_with(power_motor=True)
        west.disable.assert_called_once_with(power_motor=True)

    def test_curtains_in_danger_or_error_are_disabled_too(self):
        east, west = self._disable(CurtainStatus.CURTAIN_DANGER, CurtainStatus.CURTAIN_ERROR)

        east.disable.assert_called_once_with(power_motor=True)
        west.disable.assert_called_once_with(power_motor=True)


class TestCurtainsRoofHandler(unittest.TestCase):

    def test_a_roof_not_open_disables_the_curtains_without_powering_their_motors(self):
        east, west = MagicMock(), MagicMock()
        mediator = SimpleNamespace(button_east=east, button_west=west, is_disabled=False)
        with (
            patch("crac_server.handler.curtains_handler.roof") as roof,
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            roof.return_value.get_status.return_value = RoofStatus.ROOF_CLOSED
            CurtainsRoofHandler().handle(mediator)

        east.disable.assert_called_once_with()
        west.disable.assert_called_once_with()


class TestCurtainsMoveHandler(unittest.TestCase):

    def test_full_opening_uses_the_travel_the_curtains_read_at_startup(self):
        east, west = MagicMock(full_travel=180), MagicMock(full_travel=180)
        mediator = SimpleNamespace(is_disabled=False, button_east=east, button_west=west)
        scope = MagicMock(speed=TelescopeSpeed.SPEED_TRACKING, status=TelescopeStatus.EAST)
        scope.aa_coords.alt = 80
        scope.is_below_curtains_area.return_value = False
        scope.is_above_curtains_area.return_value = True
        with (
            patch("crac_server.handler.curtains_handler.telescope", return_value=scope),
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            CurtainsMoveHandler().handle(mediator)

        east.move.assert_called_once_with(180)
        west.move.assert_called_once_with(180)


if __name__ == "__main__":
    unittest.main()
