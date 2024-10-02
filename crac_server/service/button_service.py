import logging
from crac_protobuf.button_pb2 import (
    ButtonRequest,  # type: ignore
    ButtonAction,  # type: ignore
    ButtonType,  # type: ignore
    ButtonsResponse,  # type: ignore
)
from crac_protobuf.button_pb2_grpc import ButtonServicer
from crac_server.converter.button_converter import ButtonMediator
from crac_server.handler.button_handler import (
    ButtonActionHandler, 
    ButtonFlatHandler, 
    ButtonTelescopeHandler, 
    ButtonWeatherHandler,
)
import asyncio


logger = logging.getLogger(__name__)


class ButtonService(ButtonServicer):
    async def SetAction(self, request: ButtonRequest, context):
        logger.debug("Request " + str(request))
        button_mediator = ButtonMediator(request)

        weather_handler = ButtonWeatherHandler()
        telescope_handler = ButtonTelescopeHandler()
        flat_handler = ButtonFlatHandler()
        button_action_handler = ButtonActionHandler()
        weather_handler.set_next(telescope_handler).set_next(flat_handler).set_next(button_action_handler)
        
        return weather_handler.handle(button_mediator)

    async def GetStatus(self, request, context):
        tele_switch_button = self.SetAction(
            request = ButtonRequest(
                action=ButtonAction.CHECK_BUTTON,
                type=ButtonType.TELE_SWITCH,
            ),
            context=context,
        )
        ccd_switch_button = self.SetAction(
            request = ButtonRequest(
                action=ButtonAction.CHECK_BUTTON,
                type=ButtonType.CCD_SWITCH,
            ),
            context=context,
        )
        flat_ligth_button = self.SetAction(
            request = ButtonRequest(
                action=ButtonAction.CHECK_BUTTON,
                type=ButtonType.FLAT_LIGHT,
            ),
            context=context,
        )
        dome_light_button = self.SetAction(
            request = ButtonRequest(
                action=ButtonAction.CHECK_BUTTON,
                type=ButtonType.DOME_LIGHT,
            ),
            context=context,
        )
        buttons = await asyncio.gather(tele_switch_button, ccd_switch_button, flat_ligth_button, dome_light_button)
        return ButtonsResponse(buttons=buttons)