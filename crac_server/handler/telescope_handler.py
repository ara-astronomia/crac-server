import logging
from crac_protobuf.button_pb2 import (
    ButtonStatus,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeAction,  # type: ignore
    TelescopeResponse,  # type: ignore
    TelescopeSpeed,  # type: ignore
    TelescopeStatus,  # type: ignore
)
from crac_server.component.button_control import SWITCHES
from crac_server.handler.handler import AbstractHandler
from crac_server.converter.telescope_converter import TelescopeConverter, TelescopeMediator


logger = logging.getLogger(__name__)


class AbstractTelescopeHandler(AbstractHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if self._next_handler:
            return self._next_handler.handle(mediator)
        
        return TelescopeConverter().convert(mediator)


class TelescopeSwitchHandler(AbstractTelescopeHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if SWITCHES["TELE_SWITCH"].get_status() is ButtonStatus.OFF:
            mediator.connect_is_disabled = True
            mediator.sync_is_disabled = True
            mediator.park_is_disabled = True
            mediator.flat_is_disabled = True
            mediator.status = TelescopeStatus.LOST
            mediator.speed = TelescopeSpeed.SPEED_ERROR
            self._next_handler = None
        
        return super().handle(mediator)


class TelescopeConnectHandler(AbstractTelescopeHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if mediator.action is TelescopeAction.TELESCOPE_CONNECT:
            mediator.button.polling_start()
            self._next_handler = None
        
        return super().handle(mediator)


class TelescopeDisconnectedHandler(AbstractTelescopeHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if mediator.status is TelescopeStatus.DISCONNECTED or not mediator.button.polling:
            mediator.speed=TelescopeSpeed.SPEED_ERROR
            self._next_handler = None

        return super().handle(mediator)


class TelescopeDisconnectHandler(AbstractTelescopeHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if mediator.action is TelescopeAction.TELESCOPE_DISCONNECT:
            mediator.button.polling_end()
            self._next_handler = None
        
        return super().handle(mediator)


class TelescopeSyncHandler(AbstractTelescopeHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if mediator.action is TelescopeAction.SYNC:
            mediator.button.queue_sync(SWITCHES["TELE_SWITCH"].turned_on_at)
        
        return super().handle(mediator)


class TelescopeParkHandler(AbstractTelescopeHandler):
    def handle(self,  mediator: TelescopeMediator) -> TelescopeResponse:
        if mediator.action is TelescopeAction.PARK_POSITION:
            mediator.button.queue_park()
        
        return super().handle(mediator)


class TelescopeFlatHandler(AbstractTelescopeHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if mediator.action is TelescopeAction.FLAT_POSITION:
            mediator.button.queue_flat()
        
        return super().handle(mediator)


class TelescopeFlatterHandler(AbstractTelescopeHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if (
                mediator.status is TelescopeStatus.FLATTER and 
                SWITCHES["FLAT_LIGHT"].get_status() is ButtonStatus.ON
            ):
            mediator.button.queue_set_speed(TelescopeSpeed.SPEED_TRACKING)

        return super().handle(mediator)


class TelescopeAutolightHandler(AbstractTelescopeHandler):
    def handle(self, mediator: TelescopeMediator) -> TelescopeResponse:
        if mediator.request.autolight:
            if mediator.speed is TelescopeSpeed.SPEED_SLEWING:
                SWITCHES["DOME_LIGHT"].on()
            else:
                SWITCHES["DOME_LIGHT"].off()

        return super().handle(mediator)
