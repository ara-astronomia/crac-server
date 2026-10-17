import logging
from crac_server.component.telescope import telescope
from crac_server.converter.button_converter import (
    ButtonConverter, 
    ButtonMediator,
)
from crac_server.handler.handler import AbstractHandler
from crac_protobuf.button_pb2 import (
    ButtonAction,  # type: ignore
    ButtonType,  # type: ignore
    ButtonResponse,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeSpeed,  # type: ignore
    TelescopeStatus,  # type: ignore
)


logger = logging.getLogger(__name__)


class AbstractButtonHandler(AbstractHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if self._next_handler:
            return self._next_handler.handle(mediator)
        
        return ButtonConverter().convert(mediator)


class ButtonTelescopeHandler(AbstractButtonHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if (
            mediator.type == ButtonType.TELE_SWITCH and
            mediator.action == ButtonAction.TURN_OFF
        ):
            logger.debug("Turned off telescope connection when telescope is turned off")
            telescope().polling_end()

        return super().handle(mediator)


class ButtonFlatHandler(AbstractButtonHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if (
            mediator.type == ButtonType.FLAT_LIGHT and
            mediator.action is ButtonAction.TURN_ON and
            telescope().status is TelescopeStatus.FLATTER
        ):
            logger.debug("Track telescope on when Flat Panel is switched on")
            telescope().queue_set_speed(TelescopeSpeed.SPEED_TRACKING)

        return super().handle(mediator)


class ButtonActionHandler(AbstractButtonHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:         
        if mediator.action == ButtonAction.TURN_ON:
            mediator.button.on()
            self._next_handler = None
        elif mediator.action == ButtonAction.TURN_OFF:
            mediator.button.off()
            self._next_handler = None

        return super().handle(mediator)
