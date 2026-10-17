import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.button_pb2 import (
    ButtonAction,
    ButtonRequest,
    ButtonStatus,
    ButtonType,
)
from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.service.button_service import ButtonService

CONVERTER = "crac_server.converter.button_converter"
HANDLER = "crac_server.handler.button_handler"


class TestButtonServiceInDangerousWeather(unittest.IsolatedAsyncioTestCase):
    """Only the roof button can be disabled: the telescope supply stays
    available to the operator even in dangerous weather, for example to
    recover a blocked emergency closure by hand."""

    def setUp(self):
        self.tele_switch = MagicMock()
        self.tele_switch.get_status.return_value = ButtonStatus.OFF
        for target, double in {
            f"{CONVERTER}.switches": {"TELE_SWITCH": self.tele_switch},
            f"{HANDLER}.telescope": MagicMock(),
        }.items():
            patcher = patch(target, return_value=double)
            patcher.start()
            self.addCleanup(patcher.stop)
        weather_response = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER)
        converter_patcher = patch.object(WeatherConverter, "convert", return_value=weather_response)
        converter_patcher.start()
        self.addCleanup(converter_patcher.stop)

    async def _set_action(self, action):
        return await ButtonService().SetAction(
            ButtonRequest(action=action, type=ButtonType.TELE_SWITCH), None
        )

    async def test_the_telescope_supply_button_stays_enabled_when_turned_on(self):
        response = await self._set_action(ButtonAction.TURN_ON)

        self.assertIs(False, response.button_gui.is_disabled)
        self.tele_switch.on.assert_called_once_with()

    async def test_the_telescope_supply_button_stays_enabled_when_polled(self):
        response = await self._set_action(ButtonAction.CHECK_BUTTON)

        self.assertIs(False, response.button_gui.is_disabled)
        self.tele_switch.on.assert_not_called()


if __name__ == "__main__":
    unittest.main()
