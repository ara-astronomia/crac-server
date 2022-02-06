import logging
from crac_protobuf.roof_pb2 import (
    RoofAction,
    RoofResponse,
)
from crac_protobuf.roof_pb2_grpc import (
    RoofServicer,
)
from crac_server.component.roof.simulator.roof_control import MockRoofControl as RoofControl


logger = logging.getLogger(__name__)


class RoofService(RoofServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        if request.action == RoofAction.OPEN:
            status = RoofControl().open()
        elif request.action == RoofAction.CLOSE:
            status = RoofControl().close()
        else:
            status = RoofControl().read()

        logger.info("Response " + str(status))

        return RoofResponse(status=status)
