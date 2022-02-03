from crac_protobuf.roof_pb2 import (
    RoofAction,
    RoofResponse,
)
from crac_protobuf.roof_pb2_grpc import (
    RoofServicer,
)
from crac_server.component.mock.roof_control import MockRoofControl as RoofControl


class RoofService(RoofServicer):
    def SetAction(self, request, context):
        print("Request " + str(request))
        if request.action == RoofAction.OPEN:
            status = RoofControl().open()
        elif request.action == RoofAction.CLOSE:
            status = RoofControl().close()
        else:
            status = RoofControl().read()

        print("Response " + str(status))

        return RoofResponse(status=status)
