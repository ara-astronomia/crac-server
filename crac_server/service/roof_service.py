import logging
from crac_protobuf.button_pb2 import (
    ButtonGui,
    ButtonColor,
    ButtonLabel,
    ButtonKey,
    ButtonStatus,
)
from crac_protobuf.curtains_pb2 import CurtainStatus
from crac_protobuf.roof_pb2 import (
    RoofAction,
    RoofResponse,
    RoofStatus,
)
from crac_protobuf.roof_pb2_grpc import (
    RoofServicer,
)
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,
)
from crac_server.component.button_control import SWITCHES
from crac_server.component.curtains.factory_curtain import CURTAIN_EAST, CURTAIN_WEST
from crac_server.component.roof.simulator.roof_control import ROOF
from crac_server.component.telescope.indi.telescope import TELESCOPE


logger = logging.getLogger(__name__)


class RoofService(RoofServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        telescope_is_secure = self.__telescope_is_secure()
        curtains_are_secure = self.__curtains_are_secure()
        if request.action is RoofAction.OPEN:
            ROOF.open()
        elif (
                request.action is RoofAction.CLOSE and
                curtains_are_secure and
                telescope_is_secure
            ):
            ROOF.close()
        status = ROOF.get_status()
        logger.info("Response " + str(status))

        if status in [RoofStatus.ROOF_OPENED, RoofStatus.ROOF_OPENING]:
            text_color, background_color = ("white", "green")
        else:
            text_color, background_color = ("white", "red")

        if (
                status in [RoofStatus.ROOF_OPENING, RoofStatus.ROOF_CLOSING] or
                (
                    status is RoofStatus.ROOF_OPENED and 
                    (
                        not telescope_is_secure or
                        not curtains_are_secure
                    )
                )
        ):
            disabled = True
        else:
            disabled = False

        match status:
            case RoofStatus.ROOF_CLOSED:
                label = ButtonLabel.LABEL_CLOSE
            case RoofStatus.ROOF_OPENED:
                label = ButtonLabel.LABEL_OPEN
            case RoofStatus.ROOF_CLOSING:
                label = ButtonLabel.LABEL_CLOSING
            case RoofStatus.ROOF_OPENING:
                label = ButtonLabel.LABEL_OPENING

        button_gui = ButtonGui(
            key=ButtonKey.KEY_ROOF,
            label=label,
            metadata=(RoofAction.CLOSE if status in [RoofStatus.ROOF_OPENED, RoofStatus.ROOF_OPENING] else RoofAction.OPEN),
            is_disabled=disabled,
            button_color=ButtonColor(text_color=text_color, background_color=background_color),
        )

        return RoofResponse(status=status, button_gui=button_gui)

    def __telescope_is_secure(self):
        return (
            TELESCOPE.get_status(TELESCOPE.get_aa_coords()) <= TelescopeStatus.SECURE and
            SWITCHES["TELE_SWITCH"].get_status() is ButtonStatus.ON
        )

    def __curtains_are_secure(self):
        return (
            CURTAIN_EAST.get_status() is CurtainStatus.CURTAIN_DISABLED and 
            CURTAIN_WEST.get_status() is CurtainStatus.CURTAIN_DISABLED
        )