import logging
from crac_protobuf.curtains_pb2 import CurtainStatus
from crac_protobuf.roof_pb2 import (
    RoofAction,
    RoofResponse,
)
from crac_protobuf.roof_pb2_grpc import (
    RoofServicer,
)
from crac_server.component.curtains.factory_curtain import CURTAIN_EAST, CURTAIN_WEST
from crac_server.component.roof.simulator.roof_control import ROOF


logger = logging.getLogger(__name__)


class RoofService(RoofServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        if request.action is RoofAction.OPEN:
            ROOF.open()
        elif (
                request.action is RoofAction.CLOSE and
                CURTAIN_EAST.get_status() is CurtainStatus.CURTAIN_DISABLED and
                CURTAIN_WEST.get_status() is CurtainStatus.CURTAIN_DISABLED
            ):
            ROOF.close()
        status = ROOF.get_status()
        logger.info("Response " + str(status))

        return RoofResponse(status=status)
