import logging
from crac_protobuf.button_pb2 import (
    ButtonAction,
    ButtonType,
    ButtonResponse,
    ButtonsResponse,
)
from crac_protobuf.button_pb2_grpc import ButtonServicer

from crac_server.component.button_control import (
    TELE_SWITCH,
    CCD_SWITCH,
    FLAT_LIGHT,
    DOME_LIGHT,
)


logger = logging.getLogger(__name__)


class ButtonService(ButtonServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        if request.type == ButtonType.TELE_SWITCH:
            buttonControl = TELE_SWITCH
        elif request.type == ButtonType.CCD_SWITCH:
            buttonControl = CCD_SWITCH
        elif request.type == ButtonType.FLAT_LIGHT:
            buttonControl = FLAT_LIGHT
        elif request.type == ButtonType.DOME_LIGHT:
            buttonControl = DOME_LIGHT

        if request.action == ButtonAction.TURN_ON:
            buttonControl.on()
        elif request.action == ButtonAction.TURN_OFF:
            buttonControl.off()

        status = buttonControl.get_status()
        logger.info("Response " + str(status))

        return ButtonResponse(status=status, type=request.type)

    def GetStatus(self, request, context):
        tele_switch_button = ButtonResponse(type=ButtonType.TELE_SWITCH, status=TELE_SWITCH.get_status())
        ccd_switch_button = ButtonResponse(type=ButtonType.CCD_SWITCH, status=CCD_SWITCH.get_status())
        flat_ligth_button = ButtonResponse(type=ButtonType.FLAT_LIGHT, status=FLAT_LIGHT.get_status())
        dome_light_button = ButtonResponse(type=ButtonType.DOME_LIGHT, status=DOME_LIGHT.get_status())

        return ButtonsResponse(buttons=(tele_switch_button, ccd_switch_button, flat_ligth_button, dome_light_button))