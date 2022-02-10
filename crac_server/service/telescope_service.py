import logging
from crac_protobuf.telescope_pb2 import (
    TelescopeAction,
    TelescopeResponse,
)
from crac_protobuf.telescope_pb2_grpc import (
    TelescopeServicer,
)
from crac_server.component.telescope.simulator.telescope import TELESCOPE
from crac_server.component.button_control import TELE_SWITCH


logger = logging.getLogger(__name__)


class TelescopeService(TelescopeServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        
        if request.action == TelescopeAction.SYNC:
            TELE_SWITCH.on()
            TELESCOPE.sync()
        elif request.action == TelescopeAction.PARK_POSITION:
            TELESCOPE.park()
        elif request.action == TelescopeAction.FLAT_POSITION:
            TELESCOPE.flat()
        
        speed = TELESCOPE.get_speed()
        aa_coords = TELESCOPE.get_aa_coords()
        status = TELESCOPE.get_status(aa_coords)
        sync = TELESCOPE.sync_status

        response = TelescopeResponse(status=status, aa_coords=aa_coords, speed=speed, sync=sync)

        logger.info("Response " + str(response))

        return response
