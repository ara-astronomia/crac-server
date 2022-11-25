import logging
from crac_server.component.curtains.factory_curtain import (
    CURTAIN_EAST, 
    CURTAIN_WEST,
)
from crac_server.component.telescope import TELESCOPE
from crac_server.handler.handler import AbstractHandler
from crac_protobuf.curtains_pb2 import CurtainStatus  # type: ignore
from crac_protobuf.roof_pb2 import (
    RoofAction,  # type: ignore
    RoofResponse,  # type: ignore
    RoofStatus,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,  # type: ignore
)
from crac_server.converter.roof_converter import (
    RoofConverter, 
    RoofMediator,
)


logger = logging.getLogger(__name__)


class AbstractButtonHandler(AbstractHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if self._next_handler:
            return self._next_handler.handle(mediator)
        
        return RoofConverter().convert(mediator)

class RoofTelescopeHandler(AbstractButtonHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if (
            mediator.status is RoofStatus.ROOF_OPENED and
            not self.__telescope_is_secure()
        ):
            self._next_handler = None
            mediator.is_disabled = True
            
        return super().handle(mediator)

    def __telescope_is_secure(self):
        return (
            TELESCOPE.status <= TelescopeStatus.SECURE and
            TELESCOPE.polling
        )

class RoofCurtainsHandler(AbstractButtonHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if (
            mediator.status is RoofStatus.ROOF_OPENED and
            not self.__curtains_are_secure()
        ):
            self._next_handler = None
            mediator.is_disabled = True

        return super().handle(mediator)

    def __curtains_are_secure(self):
        return (
            CURTAIN_EAST.get_status() is CurtainStatus.CURTAIN_DISABLED and 
            CURTAIN_WEST.get_status() is CurtainStatus.CURTAIN_DISABLED
        )

class RoofHandler(AbstractButtonHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if mediator.status in [RoofStatus.ROOF_OPENING, RoofStatus.ROOF_CLOSING]:
            self._next_handler = None
            mediator.is_disabled = True
        elif mediator.action is RoofAction.OPEN:
            mediator.button.open()
        elif mediator.action is RoofAction.CLOSE:
            mediator.button.close()

        return super().handle(mediator)