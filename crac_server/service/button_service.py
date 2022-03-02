import importlib
import logging
from crac_protobuf.button_pb2 import (
    ButtonRequest,
    ButtonAction,
    ButtonType,
    ButtonResponse,
    ButtonsResponse,
    ButtonStatus,
    ButtonGui,
    ButtonColor,
    ButtonLabel,
    ButtonKey,
)
from crac_protobuf.button_pb2_grpc import ButtonServicer
from crac_protobuf.telescope_pb2 import (
    TelescopeSpeed,
    TelescopeStatus,
)
from crac_server.component.button_control import SWITCHES
from crac_server.config import Config


logger = logging.getLogger(__name__)
TELESCOPE = importlib.import_module(f"component.telescope.{Config.getValue('driver', 'telescope')}.telescope").TELESCOPE


class ButtonService(ButtonServicer):
    def SetAction(self, request: ButtonRequest, context):
        logger.info("Request " + str(request))
        button_control = SWITCHES[ButtonType.Name(request.type)]

        if request.action == ButtonAction.TURN_ON:
            button_control.on()
            if (
                request.type == ButtonType.FLAT_LIGHT and
                TELESCOPE.get_status(TELESCOPE.get_aa_coords()) is TelescopeStatus.FLATTER
            ):
                logger.info("Turned on Flat Panel")
                TELESCOPE.set_speed(TelescopeSpeed.SPEED_TRACKING)
        elif request.action == ButtonAction.TURN_OFF:
            if request.type == ButtonType.TELE_SWITCH:
                TELESCOPE.nosync()
                TELESCOPE.disconnect()
            button_control.off()

        status = button_control.get_status()
        logger.info("Response " + str(status))

        if status is ButtonStatus.ON:
            text_color, background_color = ("white", "green")
        else:
            text_color, background_color = ("white", "red")

        button_gui = ButtonGui(
            key=ButtonKey.Value(f"KEY_{ButtonType.Name(request.type)}"),
            label=(ButtonLabel.LABEL_ON if status is ButtonStatus.ON else ButtonLabel.LABEL_OFF),
            metadata=(ButtonAction.TURN_OFF if status is ButtonStatus.ON else ButtonAction.TURN_ON),
            is_disabled=False,
            button_color=ButtonColor(text_color=text_color, background_color=background_color),
        )

        return ButtonResponse(
            status=status, 
            type=request.type, 
            button_gui=button_gui
        )

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