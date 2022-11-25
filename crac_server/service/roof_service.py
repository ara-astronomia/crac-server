import logging
from crac_protobuf.roof_pb2_grpc import RoofServicer
from crac_server.converter.roof_converter import RoofMediator
from crac_server.handler.roof_handler import (
    RoofCurtainsHandler, 
    RoofHandler, 
    RoofTelescopeHandler,
)


logger = logging.getLogger(__name__)


class RoofService(RoofServicer):
    def SetAction(self, request, context):
        logger.debug("Request " + str(request))
        roof_mediator = RoofMediator(request)
        roof_telescope_handler = RoofTelescopeHandler()
        roof_curtins_handler = RoofCurtainsHandler()
        roof_handler = RoofHandler()
        roof_telescope_handler.set_next(roof_curtins_handler).set_next(roof_handler)

        return roof_telescope_handler.handle(roof_mediator)