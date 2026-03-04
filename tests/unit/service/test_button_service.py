import unittest
from unittest.mock import MagicMock, patch
from crac_protobuf.button_pb2 import (
    ButtonAction,
    ButtonRequest,
    ButtonType,
    ButtonStatus,
)
from crac_protobuf.chart_pb2 import WeatherStatus
from crac_server.service.button_service import ButtonService


class TestButtonService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.button_service = ButtonService()

    @patch("crac_server.converter.button_converter.SWITCHES")
    @patch("crac_server.handler.button_handler.WEATHER")
    @patch("crac_server.converter.weather_converter.WeatherConverter.convert")
    async def test_set_action_turn_on(
        self, mock_weather_convert, mock_weather, mock_switches
    ):
        from crac_protobuf.chart_pb2 import WeatherResponse

        mock_weather_convert.return_value = WeatherResponse(
            status=WeatherStatus.WEATHER_STATUS_NORMAL
        )

        mock_button = MagicMock()
        mock_button.get_status.return_value = ButtonStatus.OFF
        mock_switches.__getitem__.return_value = mock_button

        request = ButtonRequest(
            action=ButtonAction.TURN_ON,
            type=ButtonType.TELE_SWITCH,
        )
        response = await self.button_service.SetAction(request, None)

        self.assertIsNotNone(response)

    @patch("crac_server.converter.button_converter.SWITCHES")
    @patch("crac_server.handler.button_handler.WEATHER")
    @patch("crac_server.converter.weather_converter.WeatherConverter.convert")
    async def test_set_action_turn_off(
        self, mock_weather_convert, mock_weather, mock_switches
    ):
        from crac_protobuf.chart_pb2 import WeatherResponse

        mock_weather_convert.return_value = WeatherResponse(
            status=WeatherStatus.WEATHER_STATUS_NORMAL
        )

        mock_button = MagicMock()
        mock_button.get_status.return_value = ButtonStatus.ON
        mock_switches.__getitem__.return_value = mock_button

        request = ButtonRequest(
            action=ButtonAction.TURN_OFF,
            type=ButtonType.TELE_SWITCH,
        )
        response = await self.button_service.SetAction(request, None)

        self.assertIsNotNone(response)

    @patch("crac_server.converter.button_converter.SWITCHES")
    @patch("crac_server.handler.button_handler.WEATHER")
    @patch("crac_server.converter.weather_converter.WeatherConverter.convert")
    async def test_set_action_check_button(
        self, mock_weather_convert, mock_weather, mock_switches
    ):
        from crac_protobuf.chart_pb2 import WeatherResponse

        mock_weather_convert.return_value = WeatherResponse(
            status=WeatherStatus.WEATHER_STATUS_NORMAL
        )

        mock_button = MagicMock()
        mock_button.get_status.return_value = ButtonStatus.ON
        mock_switches.__getitem__.return_value = mock_button

        request = ButtonRequest(
            action=ButtonAction.CHECK_BUTTON,
            type=ButtonType.TELE_SWITCH,
        )
        response = await self.button_service.SetAction(request, None)

        self.assertIsNotNone(response)
        self.assertEqual(response.status, ButtonStatus.ON)

    @patch("crac_server.converter.button_converter.SWITCHES")
    @patch("crac_server.handler.button_handler.WEATHER")
    @patch("crac_server.converter.weather_converter.WeatherConverter.convert")
    async def test_get_status(self, mock_weather_convert, mock_weather, mock_switches):
        from crac_protobuf.chart_pb2 import WeatherResponse

        mock_weather_convert.return_value = WeatherResponse(
            status=WeatherStatus.WEATHER_STATUS_NORMAL
        )

        mock_button = MagicMock()
        mock_button.get_status.return_value = ButtonStatus.ON
        mock_switches.__getitem__.return_value = mock_button

        request = ButtonRequest()
        response = await self.button_service.GetStatus(request, None)

        self.assertIsNotNone(response)
        self.assertEqual(len(response.buttons), 4)
