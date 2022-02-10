import logging
from crac_protobuf.roof_pb2 import (
    RoofAction,
    RoofResponse,
)
from crac_protobuf.roof_pb2_grpc import (
    RoofServicer,
)
from crac_server.component.roof.simulator.roof_control import ROOF


logger = logging.getLogger(__name__)


class RoofService(RoofServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        if request.action == RoofAction.OPEN:
            ROOF.open()
        elif request.action == RoofAction.CLOSE:
            ROOF.close()
        
        status = ROOF.get_status()
        logger.info("Response " + str(status))

        return RoofResponse(status=status)
