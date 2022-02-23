import importlib
import logging
from crac_protobuf.button_pb2 import ButtonStatus
from crac_protobuf.telescope_pb2 import (
    TelescopeAction,
    TelescopeResponse,
    TelescopeSpeed,
    TelescopeStatus,
)
from crac_protobuf.telescope_pb2_grpc import (
    TelescopeServicer,
)
from crac_server.component.button_control import DOME_LIGHT, FLAT_LIGHT, TELE_SWITCH
from crac_server.config import Config


logger = logging.getLogger(__name__)
TELESCOPE = importlib.import_module(f"component.telescope.{Config.getValue('driver', 'telescope')}.telescope").TELESCOPE


class TelescopeService(TelescopeServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        if (
                TELE_SWITCH.get_status() is ButtonStatus.OFF and
                request.action is not TelescopeAction.SYNC
            ):
            return TelescopeResponse(
                status=TelescopeStatus.LOST, 
                speed=TelescopeSpeed.SPEED_ERROR,
                sync=False
            )
        elif request.action is TelescopeAction.SYNC:
            TELE_SWITCH.on()
            TELESCOPE.sync()
        elif (
                request.action is TelescopeAction.PARK_POSITION and 
                TELE_SWITCH.get_status() is ButtonStatus.ON
        ):
            TELESCOPE.park()
        elif (
                request.action is TelescopeAction.FLAT_POSITION and
                TELE_SWITCH.get_status() is ButtonStatus.ON
        ):
            TELESCOPE.flat()

        aa_coords = TELESCOPE.get_aa_coords()
        status = TELESCOPE.get_status(aa_coords)
        sync = TELESCOPE.sync_status
        if (
                status is TelescopeStatus.PARKED or 
                (
                    status is TelescopeStatus.FLATTER and 
                    FLAT_LIGHT.get_status() is ButtonStatus.OFF
                )
            ):
            TELESCOPE.set_speed(TelescopeSpeed.SPEED_NOT_TRACKING)
        speed = TELESCOPE.get_speed()

        response = TelescopeResponse(status=status, aa_coords=aa_coords, speed=speed, sync=sync)
        logger.info("Response " + str(response))

        if request.autolight:
            if speed is TelescopeSpeed.SPEED_SLEWING:
                DOME_LIGHT.on()
            else:
                DOME_LIGHT.off()

        return response
