import unittest
from types import SimpleNamespace
from unittest.mock import patch

from crac_protobuf.button_pb2 import (
    ButtonAction,
    ButtonResponse,
    ButtonStatus,
    ButtonType,
)
from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_server.converter.button_converter import ButtonConverter
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.handler.button_handler import ButtonWeatherHandler


class TestButtonWeatherHandler(unittest.TestCase):
    """
    Switching the telescope on under dangerous weather must be refused, the
    same way opening the roof and the curtains already is.
    """

    def _handle(self, weather_status, button_type=ButtonType.TELE_SWITCH):
        mediator = SimpleNamespace(
            status=ButtonStatus.OFF,
            type=button_type,
            action=ButtonAction.TURN_ON,
            is_disabled=False,
        )
        weather_response = WeatherResponse(status=weather_status)
        with (
            patch.object(WeatherConverter, "convert", return_value=weather_response),
            patch.object(ButtonConverter, "convert", return_value=ButtonResponse()),
        ):
            ButtonWeatherHandler().handle(mediator)
        return mediator

    def test_disables_the_telescope_switch_on_dangerous_weather(self):
        self.assertIs(True, self._handle(WeatherStatus.WEATHER_STATUS_DANGER).is_disabled)

    def test_keeps_the_telescope_switch_enabled_on_normal_weather(self):
        self.assertIs(False, self._handle(WeatherStatus.WEATHER_STATUS_NORMAL).is_disabled)

    def test_leaves_other_buttons_enabled_on_dangerous_weather(self):
        mediator = self._handle(
            WeatherStatus.WEATHER_STATUS_DANGER,
            button_type=ButtonType.DOME_LIGHT,
        )
        self.assertIs(False, mediator.is_disabled)


if __name__ == "__main__":
    unittest.main()
