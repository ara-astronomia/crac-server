import logging
from crac_protobuf.telescope_pb2 import (
    TelescopeAction,
    TelescopeResponse,
)
from crac_protobuf.telescope_pb2_grpc import (
    TelescopeServicer,
)
from crac_server.component.telescope.simulator.telescope import Telescope
from crac_server.component.button_control import ButtonControl
from crac_server.config import Config


logger = logging.getLogger(__name__)
telescope = Telescope()


class TelescopeService(TelescopeServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        
        if request.action == TelescopeAction.SYNC:
            tele_switch = ButtonControl(Config.getInt("switch_power", "panel_board"))
            tele_switch.on()
            telescope.sync()
        elif request.action == TelescopeAction.PARK_POSITION:
            telescope.park()
        elif request.action == TelescopeAction.FLAT_POSITION:
            telescope.flat()
        
        speed = telescope.get_speed()
        aa_coords = telescope.get_aa_coords()
        status = telescope.get_status(aa_coords)
        sync = telescope.sync_status

        response = TelescopeResponse(status=status, aa_coords=aa_coords, speed=speed, sync=sync)

        logger.info("Response " + str(response))

        return response
