from curses import meta
import importlib
import logging
from crac_protobuf.curtains_pb2 import (
    CurtainsAction,
    CurtainsResponse,
    CurtainOrientation,
    CurtainEntryResponse,
    CurtainStatus,
)
from crac_protobuf.button_pb2 import (
    ButtonGui,
    ButtonLabel,
    ButtonKey,
    ButtonColor,
    ButtonStatus,
)
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,
    TelescopeSpeed,
)
from crac_protobuf.curtains_pb2_grpc import CurtainServicer
from crac_protobuf.roof_pb2 import RoofStatus
from crac_server.component.button_control import SWITCHES
from crac_server.component.curtains.factory_curtain import (
    CURTAIN_EAST,
    CURTAIN_WEST,
)
from crac_server.component.roof import ROOF
from crac_server.component.telescope import TELESCOPE
from crac_server.config import Config


logger = logging.getLogger(__name__)


class CurtainsService(CurtainServicer):
    def SetAction(self, request, context):
        logger.info("Request " + str(request))
        
        roof_is_opened = ROOF.get_status() is RoofStatus.ROOF_OPENED
        tele_is_turned_on = SWITCHES["TELE_SWITCH"].get_status() is ButtonStatus.ON
        
        curtain_east_entry = CurtainEntryResponse(orientation=CurtainOrientation.CURTAIN_EAST)
        curtain_west_entry = CurtainEntryResponse(orientation=CurtainOrientation.CURTAIN_WEST)
        if request.action is CurtainsAction.DISABLE:
            statusE = CURTAIN_EAST.get_status()
            statusW = CURTAIN_WEST.get_status()
            if (
                statusE <= CurtainStatus.CURTAIN_OPENED and
                statusW <= CurtainStatus.CURTAIN_OPENED
            ):
                CURTAIN_EAST.disable()
                CURTAIN_WEST.disable()
        elif (
                request.action is CurtainsAction.ENABLE and
                roof_is_opened
        ):
            CURTAIN_EAST.enable()
            CURTAIN_WEST.enable()
        # elif request.action is CurtainsAction.CALIBRATE_CURTAINS:
        #     CURTAIN_EAST.manual_reset()
        #     CURTAIN_WEST.manual_reset()

        if TELESCOPE.speed in (TelescopeSpeed.SPEED_TRACKING, TelescopeSpeed.SPEED_NOT_TRACKING):
            steps = self.__calculate_curtains_steps()
            CURTAIN_EAST.move(steps["east"])
            CURTAIN_WEST.move(steps["west"])

        curtain_east_entry.status = CURTAIN_EAST.get_status()
        curtain_west_entry.status = CURTAIN_WEST.get_status()
        curtain_east_entry.steps = CURTAIN_EAST.steps()
        curtain_west_entry.steps = CURTAIN_WEST.steps()
        logger.debug("actual east curtain steps %s", curtain_east_entry.steps)
        logger.debug("actual west curtain steps %s", curtain_west_entry.steps)
        if (
            curtain_east_entry.status is CurtainStatus.CURTAIN_DISABLED and 
            curtain_west_entry.status is CurtainStatus.CURTAIN_DISABLED
        ):
            metadata_enable_button = CurtainsAction.ENABLE
            name_enable_button = ButtonLabel.LABEL_DISABLE
            text_color, background_color = ("white", "red")
        else:
            metadata_enable_button = CurtainsAction.DISABLE
            name_enable_button = ButtonLabel.LABEL_ENABLE
            text_color, background_color = ("white", "green")
            
        enable_button = ButtonGui(
            key=ButtonKey.KEY_CURTAINS,
            label=name_enable_button,
            metadata=metadata_enable_button,
            is_disabled=(not roof_is_opened),
            button_color=ButtonColor(text_color=text_color, background_color=background_color),
        )

        calibrate_button = ButtonGui(
            key=ButtonKey.KEY_CALIBRATE,
            label=ButtonLabel.LABEL_CALIBRATE,
            is_disabled=True,
            metadata=CurtainsAction.CALIBRATE_CURTAINS,
            button_color=ButtonColor(text_color="white", background_color="red"),
        )

        return CurtainsResponse(
            curtains=(
                curtain_east_entry, 
                curtain_west_entry
            ), 
            buttons_gui=[
                enable_button, 
                calibrate_button
            ]
        )

    def __calculate_curtains_steps(self):

        """
            Change the height of the curtains
            to based on the given Coordinates
        """

        aa_coords = TELESCOPE.aa_coords
        status = TELESCOPE.status
        steps = {}
        logger.debug("Telescope status %s", status)
        n_step_corsa = Config.getInt('n_step_corsa', "encoder_step")
        # TODO verify tele height:
        # if less than east_min_height e ovest_min_height
        if status in [TelescopeStatus.LOST, TelescopeStatus.ERROR]:
            steps["west"] = None
            steps["east"] = None

        if TELESCOPE.is_below_curtains_area(aa_coords.alt):
            #   keep both curtains to 0
            steps["west"] = 0
            steps["east"] = 0

            #   else if higher to east_max_height e ovest_max_height
        elif TELESCOPE.is_above_curtains_area(aa_coords.alt, Config.getInt("max_est", "tende"), Config.getInt("max_west", "tende")) or not TELESCOPE.is_within_curtains_area():
            #   move both curtains max open
            steps["west"] = n_step_corsa
            steps["east"] = n_step_corsa

            #   else if higher to ovest_min_height and Az tele to west
        elif status == TelescopeStatus.WEST:
            logger.debug("inside west status")
            #   move curtain east max open
            steps["east"] = n_step_corsa
            #   move curtain west to f(Alt telescope - x)
            increm_w = (Config.getInt("max_west", "tende") - Config.getInt("park_west", "tende")) / n_step_corsa
            steps["west"] = round((aa_coords.alt - Config.getInt("park_west", "tende"))/increm_w)

            #   else if higher to ovest_min_height and Az tele to est
        elif status == TelescopeStatus.EAST:
            logger.debug("inside east status")
            #   move curtian west max open
            steps["west"] = n_step_corsa
            #   if inferior to est_min_height
            #   move curtain east to f(Alt tele - x)
            increm_e = (Config.getInt("max_est", "tende") - Config.getInt("park_est", "tende")) / n_step_corsa
            steps["east"] = round((aa_coords.alt - Config.getInt("park_est", "tende")) / increm_e)

        logger.debug("calculatd curtain steps %s", steps)

        return steps