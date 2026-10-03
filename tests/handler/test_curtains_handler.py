import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_protobuf.curtains_pb2 import CurtainsAction, CurtainsResponse, CurtainStatus
from crac_protobuf.telescope_pb2 import TelescopeSpeed, TelescopeStatus
from crac_server.converter.curtains_converter import CurtainsConverter
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.handler.curtains_handler import CurtainsMoveHandler, CurtainsWeatherHandler


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
