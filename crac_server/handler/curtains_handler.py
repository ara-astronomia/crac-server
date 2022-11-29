import logging
from crac_protobuf.curtains_pb2 import (
    CurtainsAction,  # type: ignore
    CurtainsResponse,  # type: ignore
    CurtainStatus,  # type: ignore
)
from crac_protobuf.roof_pb2 import (
    RoofStatus,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeSpeed,  # type: ignore
    TelescopeStatus,  # type: ignore
)
from crac_protobuf.chart_pb2 import (
    WeatherStatus,  # type: ignore
)
from crac_server.component.roof import ROOF
from crac_server.component.telescope import TELESCOPE
from crac_server.component.weather import WEATHER
from crac_server.config import Config
from crac_server.converter.curtains_converter import CurtainsConverter, CurtainsMediator
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.handler.handler import AbstractHandler


logger = logging.getLogger(__name__)


class AbstractCurtainsHandler(AbstractHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:
        if self._next_handler:
            return self._next_handler.handle(mediator)
        
        return CurtainsConverter().convert(mediator)

class CurtainsRoofHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:
        roof_is_opened = ROOF.get_status() is RoofStatus.ROOF_OPENED

        if not roof_is_opened:
            mediator.button_east.disable()
            mediator.button_west.disable()
            mediator.is_disabled = True
            self._next_handler = None
        
        return super().handle(mediator)

class CurtainsWeatherHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:
        logger.info("In weather handler")

        if (
            mediator.status_east is CurtainStatus.CURTAIN_DISABLED and
            mediator.status_west is CurtainStatus.CURTAIN_DISABLED
        ):
            logger.info(f"In turn on or check action {mediator.action}")
            weather_converter = WeatherConverter()
            weather_response = weather_converter.convert(WEATHER)
            logger.info(f"In weather status {weather_response.status}")
            if weather_response.status == WeatherStatus.WEATHER_STATUS_DANGER:
                logger.info(f"In status danger {weather_response.status}")
                mediator.is_disabled = True
                self._next_handler = None

        return super().handle(mediator)

class CurtainsTelescopeHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:    
        if not TELESCOPE.polling:
            mediator.button_east.disable()
            mediator.button_west.disable()
            mediator.is_disabled = True
            self._next_handler = None

        return super().handle(mediator)

class CurtainsDisableHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:
        if mediator.action is CurtainsAction.DISABLE:
            if (
                mediator.status_east <= CurtainStatus.CURTAIN_OPENED and
                mediator.status_west <= CurtainStatus.CURTAIN_OPENED
            ):
                mediator.button_east.disable()
                mediator.button_west.disable()
        
        return super().handle(mediator)
    
class CurtainsEnableHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:

        if (
                mediator.action is CurtainsAction.ENABLE
        ):
            mediator.button_east.enable()
            mediator.button_west.enable()
        
        return super().handle(mediator)

class CurtainsCalibrationHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:
        
        # TODO check if manual calibration is needed and in case create a story for it
        # elif request.action is CurtainsAction.CALIBRATE_CURTAINS:
        #     CURTAIN_EAST.manual_reset()
        #     CURTAIN_WEST.manual_reset()

        return super().handle(mediator)

class CurtainsMoveHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:

        if TELESCOPE.speed in (TelescopeSpeed.SPEED_TRACKING, TelescopeSpeed.SPEED_NOT_TRACKING):
            steps = self.__calculate_curtains_steps()
            mediator.button_east.move(steps["east"])
            mediator.button_west.move(steps["west"])

        return super().handle(mediator)
    
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
