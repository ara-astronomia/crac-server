from crac_protobuf.button_pb2 import (
    ButtonAction,
    ButtonType,
    ButtonResponse,
    ButtonStatus
)
from crac_protobuf.button_pb2_grpc import ButtonServicer


class ButtonService(ButtonServicer):
    def SetAction(self, request, context):
        print("Request " + str(request.action))
        #if request.type == ButtonType.CCD_SWITCH:
        #     status = RoofControl().open()
        if request.action == ButtonAction.TURN_ON:
            status = ButtonStatus.ON
        elif request.action == ButtonAction.TURN_OFF:
            status = ButtonStatus.OFF
        # elif request.type == ButtonType.TELE_SWITCH:
        #     pass
        # elif request.type == ButtonType.FLAT_LIGHT:
        #     pass
        # elif request.type == ButtonType.DOME_LIGHT:
        #     pass

        print("Response " + str(status))

        return ButtonResponse(status=status)
