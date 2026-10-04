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
from crac_server.component.roof import roof
from crac_server.component.telescope import telescope
from crac_server.component.weather import weather
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
        roof_is_opened = roof().get_status() is RoofStatus.ROOF_OPENED

        if not roof_is_opened:
            mediator.curtain_east.disable()
            mediator.curtain_west.disable()
            mediator.is_disabled = True
            self._next_handler = None
        
        return super().handle(mediator)

class CurtainsWeatherHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:
        logger.debug("In weather handler")

        if (
            mediator.status_east is CurtainStatus.CURTAIN_DISABLED and
            mediator.status_west is CurtainStatus.CURTAIN_DISABLED
        ):
            logger.debug(f"In turn on or check action {mediator.action}")
            weather_converter = WeatherConverter()
            weather_response = weather_converter.convert(weather())
            logger.debug(f"Weather status: {weather_response.status}")
            logger.debug(f"Weather charts: {weather_response.charts}")
            logger.debug(f"In weather status {weather_response.status}")
            if weather_response.status == WeatherStatus.WEATHER_STATUS_DANGER or (
                Config.getRequiredBoolean("block_on_unspecified", "weather") and 
                weather_response.status == WeatherStatus.WEATHER_STATUS_UNSPECIFIED
                ):
                logger.info(f"In status danger or unspecified {weather_response.status}")
                mediator.is_disabled = True
                self._next_handler = None

        return super().handle(mediator)

class CurtainsTelescopeHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:    
        if not telescope().polling:
            mediator.curtain_east.disable()
            mediator.curtain_west.disable()
            mediator.is_disabled = True
            self._next_handler = None

        return super().handle(mediator)

class CurtainsDisableHandler(AbstractCurtainsHandler):
    """DISABLE brings each curtain down whatever it is doing, and the chain
    stops here so that no move overrides it."""

    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:
        if mediator.action is CurtainsAction.DISABLE:
            mediator.curtain_east.disable(power_motor=True)
            mediator.curtain_west.disable(power_motor=True)
            self._next_handler = None
            return super().handle(mediator)
        
        return super().handle(mediator)
    
class CurtainsEnableHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:

        if (
                mediator.action is CurtainsAction.ENABLE
        ):
            mediator.curtain_east.enable()
            mediator.curtain_west.enable()
        
        return super().handle(mediator)

class CurtainsMoveHandler(AbstractCurtainsHandler):
    def handle(self, mediator: CurtainsMediator) -> CurtainsResponse:
        if not mediator.is_disabled and telescope().speed in (TelescopeSpeed.SPEED_TRACKING, TelescopeSpeed.SPEED_NOT_TRACKING):
            steps = self.__calculate_curtains_steps(mediator.curtain_east.full_travel)
            mediator.curtain_east.move(steps["east"])
            mediator.curtain_west.move(steps["west"])

        return super().handle(mediator)
    
    def __calculate_curtains_steps(self, full_travel: int):
        """Both curtains down with the telescope parked or below their area,
        both fully open above it or outside it; otherwise the curtain on the
        telescope's side follows its altitude and the other one is open."""

        aa_coords = telescope().aa_coords
        status = telescope().status
        steps = {}
        logger.debug("Telescope status %s", status)
        if status in [TelescopeStatus.LOST, TelescopeStatus.ERROR]:
            steps["west"] = None
            steps["east"] = None
        elif status == TelescopeStatus.PARKED:
            steps["west"] = 0
            steps["east"] = 0
        elif telescope().is_below_curtains_area(aa_coords.alt):
            steps["west"] = 0
            steps["east"] = 0
        elif telescope().is_above_curtains_area(aa_coords.alt, Config.getInt("max_est", "tende"), Config.getInt("max_west", "tende")) or not telescope().is_within_curtains_area():
            steps["west"] = full_travel
            steps["east"] = full_travel
        elif status == TelescopeStatus.WEST:
            logger.debug("inside west status")
            steps["east"] = full_travel
            degrees_per_step = (Config.getInt("max_west", "tende") - Config.getInt("park_west", "tende")) / full_travel
            steps["west"] = round((aa_coords.alt - Config.getInt("park_west", "tende")) / degrees_per_step)
        elif status == TelescopeStatus.EAST:
            logger.debug("inside east status")
            steps["west"] = full_travel
            degrees_per_step = (Config.getInt("max_est", "tende") - Config.getInt("park_est", "tende")) / full_travel
            steps["east"] = round((aa_coords.alt - Config.getInt("park_est", "tende")) / degrees_per_step)

        logger.debug("calculated curtain steps %s", steps)

        return steps
