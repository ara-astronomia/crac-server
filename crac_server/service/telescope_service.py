from cgitb import text
from faulthandler import disable
import importlib
import logging
from crac_protobuf.button_pb2 import ButtonStatus
from crac_protobuf.button_pb2 import (
    ButtonGui,
    ButtonColor,
    ButtonLabel,
    ButtonKey,
)
from crac_protobuf.telescope_pb2 import (
    TelescopeAction,
    TelescopeResponse,
    TelescopeSpeed,
    TelescopeStatus,
)
from crac_protobuf.telescope_pb2_grpc import (
    TelescopeServicer,
)
from crac_server.component.button_control import SWITCHES
from crac_server.config import Config


logger = logging.getLogger(__name__)
TELESCOPE = importlib.import_module(f"component.telescope.{Config.getValue('driver', 'telescope')}.telescope").TELESCOPE


class TelescopeService(TelescopeServicer):
    def SetAction(self, request, context):
        logger.info("TelescopeRequest TelescopeService" + str(request))
        if (
                SWITCHES["TELE_SWITCH"].get_status() is ButtonStatus.OFF and
                request.action is not TelescopeAction.SYNC
            ):
            return TelescopeResponse(
                status=TelescopeStatus.LOST, 
                speed=TelescopeSpeed.SPEED_ERROR,
                sync=False,
                buttons_gui=[
                    ButtonGui(
                        key=ButtonKey.KEY_SYNC,
                        label=ButtonLabel.LABEL_SYNC,
                        metadata=TelescopeAction.SYNC,
                        button_color=ButtonColor(text_color="white", background_color="red"),
                    ),
                    ButtonGui(
                        key=ButtonKey.KEY_PARK,
                        label=ButtonLabel.LABEL_PARK,
                        metadata=TelescopeAction.PARK_POSITION,
                        is_disabled=True,
                        button_color=ButtonColor(text_color="white", background_color="red"),
                    ),
                    ButtonGui(
                        key=ButtonKey.KEY_FLAT,
                        label=ButtonLabel.LABEL_FLAT,
                        metadata=TelescopeAction.FLAT_POSITION,
                        is_disabled=True,
                        button_color=ButtonColor(text_color="white", background_color="red"),
                    ),
                ]
            )
        elif request.action is TelescopeAction.SYNC:
            SWITCHES["TELE_SWITCH"].on()
            TELESCOPE.sync()
        elif (
                request.action is TelescopeAction.PARK_POSITION and 
                SWITCHES["TELE_SWITCH"].get_status() is ButtonStatus.ON
        ):
            TELESCOPE.park()
        elif (
                request.action is TelescopeAction.FLAT_POSITION and
                SWITCHES["TELE_SWITCH"].get_status() is ButtonStatus.ON
        ):
            TELESCOPE.flat()

        aa_coords = TELESCOPE.get_aa_coords()
        status = TELESCOPE.get_status(aa_coords)
        sync = TELESCOPE.sync_status
        if (
                status is TelescopeStatus.PARKED or 
                (
                    status is TelescopeStatus.FLATTER and 
                    SWITCHES["FLAT_LIGHT"].get_status() is ButtonStatus.OFF
                )
            ):
            TELESCOPE.set_speed(TelescopeSpeed.SPEED_NOT_TRACKING)
        speed = TELESCOPE.get_speed()
        
        match status:
            case TelescopeStatus.PARKED:
                park_button_color = ButtonColor(text_color="white", background_color="green")
                flat_button_color = ButtonColor(text_color="black", background_color="white")
            case TelescopeStatus.FLATTER:
                park_button_color = ButtonColor(text_color="black", background_color="white")
                flat_button_color = ButtonColor(text_color="white", background_color="green")
            case _:
                park_button_color = ButtonColor(text_color="black", background_color="white")
                flat_button_color = ButtonColor(text_color="black", background_color="white")
        
        if TELESCOPE.sync_status:
            sync_button_color = ButtonColor(text_color="white", background_color="green")
            sync_disabled = True
        else:
            sync_button_color = ButtonColor(text_color="white", background_color="red")
            sync_disabled = False

        sync_button_gui = ButtonGui(
            key=ButtonKey.KEY_SYNC,
            label=ButtonLabel.LABEL_SYNC,
            metadata=TelescopeAction.SYNC,
            is_disabled=sync_disabled,
            button_color=sync_button_color
        )
        park_button_gui = ButtonGui(
            key=ButtonKey.KEY_PARK,
            label=ButtonLabel.LABEL_PARK,
            metadata=TelescopeAction.PARK_POSITION,
            is_disabled=False,
            button_color=park_button_color
        ) 
        flat_button_gui = ButtonGui(
            key=ButtonKey.KEY_FLAT,
            label=ButtonLabel.LABEL_FLAT,
            metadata=TelescopeAction.FLAT_POSITION,
            is_disabled=False,
            button_color=flat_button_color
        )
        response = TelescopeResponse(
            status=status, 
            aa_coords=aa_coords, 
            speed=speed, 
            sync=sync,
            buttons_gui=[
                sync_button_gui,
                park_button_gui,
                flat_button_gui,
            ]
        )
        logger.info("Response " + str(response))

        if request.autolight:
            if speed is TelescopeSpeed.SPEED_SLEWING:
                SWITCHES["DOME_LIGHT"].on()
            else:
                SWITCHES["DOME_LIGHT"].off()


        return response
