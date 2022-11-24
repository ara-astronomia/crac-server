import logging
from crac_server.component.button_control import SWITCHES
from crac_server.component.telescope import TELESCOPE
from crac_server.handler.handler import AbstractHandler
from crac_protobuf.button_pb2 import (
    ButtonRequest,
    ButtonAction,
    ButtonType,
    ButtonResponse,
    ButtonStatus,
    ButtonGui,
    ButtonColor,
    ButtonLabel,
    ButtonKey,
)
from crac_protobuf.telescope_pb2 import (
    TelescopeSpeed,
    TelescopeStatus,
)


logger = logging.getLogger(__name__)


class AbstractButtonHandler(AbstractHandler):
    def handle(self, request: ButtonRequest) -> ButtonResponse:
        if self._next_handler:
            return self._next_handler.handle(request)
        
        button_control = SWITCHES[ButtonType.Name(request.type)]
        status = button_control.get_status()

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


class ButtonActionHandler(AbstractButtonHandler):
    def handle(self, request: ButtonRequest) -> ButtonResponse:
        button_control = SWITCHES[ButtonType.Name(request.type)]
         
        if request.action == ButtonAction.TURN_ON:
            button_control.on()
        elif request.action == ButtonAction.TURN_OFF:
            button_control.off()

        return super().handle(request)


class TelescopeHandler(AbstractButtonHandler):
    def handle(self, request: ButtonRequest) -> ButtonResponse:
        button_control = SWITCHES[ButtonType.Name(request.type)]

        if (
            request.type == ButtonType.TELE_SWITCH and
            request.action == ButtonAction.TURN_OFF
        ):
        
            button_control.off()
            logger.info("Turned off telescope connection when telescope is turned off")
            TELESCOPE.polling_end()

        return super().handle(request)


class FlatHandler(AbstractButtonHandler):
    def handle(self, request: ButtonRequest) -> ButtonResponse:
        button_control = SWITCHES[ButtonType.Name(request.type)]
        status = button_control.get_status()

        if (
            request.type == ButtonType.FLAT_LIGHT and
            status is ButtonStatus.ON and
            TELESCOPE.status is TelescopeStatus.FLATTER
        ):
            button_control.on()
            logger.info("Track telescope on when Flat Panel is switched on")
            TELESCOPE.queue_set_speed(TelescopeSpeed.SPEED_TRACKING)

        return super().handle(request)
