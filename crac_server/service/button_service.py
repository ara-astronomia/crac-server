from crac_protobuf.button_pb2 import (
    ButtonAction,
    ButtonType,
    ButtonResponse,
)
from crac_protobuf.button_pb2_grpc import ButtonServicer

from crac_server.component.button_control import ButtonControl
from crac_server.config import Config


class ButtonService(ButtonServicer):
    def SetAction(self, request, context):
        print("Request " + str(request))
        if request.type == ButtonType.TELE_SWITCH:
            buttonControl = ButtonControl(Config.getInt("switch_power", "panel_board"))
        elif request.type == ButtonType.CCD_SWITCH:
            buttonControl = ButtonControl(Config.getInt("switch_aux", "panel_board"))
        elif request.type == ButtonType.FLAT_LIGHT:
            buttonControl = ButtonControl(Config.getInt("switch_panel", "panel_board"))
        elif request.type == ButtonType.DOME_LIGHT:
            buttonControl = ButtonControl(Config.getInt("switch_light", "panel_board"))

        if request.action == ButtonAction.TURN_ON:
            status = buttonControl.on()
        elif request.action == ButtonAction.TURN_OFF:
            status = buttonControl.off()

        print("Response " + str(status))

        return ButtonResponse(status=status, type=request.type)
