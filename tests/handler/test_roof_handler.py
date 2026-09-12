import unittest
from types import SimpleNamespace
from unittest.mock import patch

from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_protobuf.roof_pb2 import RoofResponse, RoofStatus
from crac_server.converter.roof_converter import RoofConverter
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.handler.roof_handler import RoofWeatherHandler


class TestRoofWeatherHandler(unittest.TestCase):
    """
    Opening the roof is refused on dangerous weather, and on unknown weather
    only when the installation asked for it.
    """

    def _handle(self, weather_status, block_on_unspecified):
        mediator = SimpleNamespace(status=RoofStatus.ROOF_CLOSED, is_disabled=False)
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


if __name__ == "__main__":
    unittest.main()
