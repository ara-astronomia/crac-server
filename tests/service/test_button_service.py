import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.button_pb2 import (
    ButtonAction,
    ButtonRequest,
    ButtonStatus,
    ButtonType,
)
from crac_protobuf.chart_pb2 import WeatherResponse, WeatherStatus
from crac_protobuf.telescope_pb2 import TelescopeStatus
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.service.button_service import ButtonService

CONVERTER = "crac_server.converter.button_converter"
HANDLER = "crac_server.handler.button_handler"
POWER_BUTTONS = (
    ButtonType.TELE_SWITCH,
    ButtonType.CCD_SWITCH,
    ButtonType.FLAT_LIGHT,
    ButtonType.DOME_LIGHT,
)
ACTIONS = (ButtonAction.TURN_ON, ButtonAction.TURN_OFF, ButtonAction.CHECK_BUTTON)


class TestPowerButtonsAreNeverDisabled(unittest.IsolatedAsyncioTestCase):
    """Only the roof button can be disabled: the power supplies and the
    lights stay available to the operator even in dangerous weather, for
    example to recover a blocked emergency closure by hand."""

    def setUp(self):
        self.buttons = {ButtonType.Name(button): MagicMock() for button in POWER_BUTTONS}
        for switch in self.buttons.values():
            switch.get_status.return_value = ButtonStatus.OFF
        telescope = MagicMock()
        telescope.status = TelescopeStatus.FLATTER
        for target, double in {
            f"{CONVERTER}.switches": self.buttons,
            f"{HANDLER}.telescope": telescope,
        }.items():
            patcher = patch(target, return_value=double)
            patcher.start()
            self.addCleanup(patcher.stop)
        weather_response = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER)
        converter_patcher = patch.object(WeatherConverter, "convert", return_value=weather_response)
        converter_patcher.start()
        self.addCleanup(converter_patcher.stop)

    async def _set_action(self, button, action):
        return await ButtonService().SetAction(ButtonRequest(action=action, type=button), None)

    async def test_no_power_button_is_disabled_whatever_the_action_and_status(self):
        for button in POWER_BUTTONS:
            for status in (ButtonStatus.ON, ButtonStatus.OFF):
                for action in ACTIONS:
                    with self.subTest(button=ButtonType.Name(button), status=ButtonStatus.Name(status), action=ButtonAction.Name(action)):
                        self.buttons[ButtonType.Name(button)].get_status.return_value = status

                        response = await self._set_action(button, action)

                        self.assertIs(False, response.button_gui.is_disabled)

    async def test_no_power_button_is_disabled_in_the_status_poll(self):
        response = await ButtonService().GetStatus(None, None)

        self.assertEqual(
            [(button, False) for button in POWER_BUTTONS],
            [(button.type, button.button_gui.is_disabled) for button in response.buttons],
        )

    async def test_the_telescope_supply_is_turned_on_in_dangerous_weather(self):
        await self._set_action(ButtonType.TELE_SWITCH, ButtonAction.TURN_ON)

        self.buttons["TELE_SWITCH"].on.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
