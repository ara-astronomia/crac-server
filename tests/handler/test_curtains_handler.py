import unittest
from types import SimpleNamespace
from unittest.mock import patch

from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_protobuf.curtains_pb2 import CurtainsAction, CurtainsResponse, CurtainStatus
from crac_server.converter.curtains_converter import CurtainsConverter
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.handler.curtains_handler import CurtainsWeatherHandler


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


if __name__ == "__main__":
    unittest.main()
