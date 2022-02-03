from crac_protobuf.telescope_pb2 import (
    TelescopeAction,
    TelescopeResponse,
)
from crac_protobuf.telescope_pb2_grpc import (
    TelescopeServicer,
)
#from crac_server.component.telescope_control import MockRoofControl as RoofControl


class TelescopeService(TelescopeServicer):
    def SetAction(self, request, context):
        print("Request " + str(request))
        sync = False
        if request.action == TelescopeAction.SYNC:
            sync = True
            #status = RoofControl().open()
        elif request.action == TelescopeAction.PARK_POSITION:
            pass
            #status = RoofControl().close()
        elif request.action == TelescopeAction.FLAT_POSITION:
            pass
        elif request.action == TelescopeAction.CHECK_TELESCOPE:
            pass
            #status = RoofControl().read()

        print("Response " + str(sync))

        return TelescopeResponse(sync=sync)
