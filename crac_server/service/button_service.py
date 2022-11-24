import logging
from crac_protobuf.button_pb2 import (
    ButtonRequest,  # type: ignore
    ButtonAction,  # type: ignore
    ButtonType,  # type: ignore
    ButtonsResponse,  # type: ignore
)
from crac_protobuf.button_pb2_grpc import ButtonServicer
from crac_server.converter.button_converter import ButtonMediator
from crac_server.handler.button_handler import ButtonActionHandler, FlatHandler, TelescopeHandler


logger = logging.getLogger(__name__)



class ButtonService(ButtonServicer):
    def SetAction(self, request: ButtonRequest, context):
        logger.debug("Request " + str(request))
        button_mediator = ButtonMediator(request)

        telescope_handler = TelescopeHandler()
        flat_handler = FlatHandler()
        button_action_handler = ButtonActionHandler()
        telescope_handler.set_next(flat_handler).set_next(button_action_handler)
        
        return telescope_handler.handle(button_mediator)

    def GetStatus(self, request, context):
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

        return ButtonsResponse(buttons=(tele_switch_button, ccd_switch_button, flat_ligth_button, dome_light_button))