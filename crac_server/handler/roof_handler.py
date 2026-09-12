import asyncio
import logging
from crac_protobuf.curtains_pb2 import CurtainStatus  # type: ignore
from crac_protobuf.roof_pb2 import (
    RoofAction,  # type: ignore
    RoofResponse,  # type: ignore
    RoofStatus,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,  # type: ignore
)
from crac_protobuf.chart_pb2 import (
    WeatherStatus,  # type: ignore
)
from crac_server.component.curtains.factory_curtain import (
    curtain_east, 
    curtain_west,
)
from crac_server.component.telescope import telescope
from crac_server.component.weather import weather
from crac_server.converter.roof_converter import (
    RoofConverter, 
    RoofMediator,
)
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.handler.handler import AbstractHandler
from crac_server.config import Config


logger = logging.getLogger(__name__)

class AbstractButtonHandler(AbstractHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if self._next_handler:
            return self._next_handler.handle(mediator)
        
        return RoofConverter().convert(mediator)


class RoofWeatherHandler(AbstractButtonHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if mediator.status is RoofStatus.ROOF_CLOSED:
            weather_converter = WeatherConverter()
            weather_response = weather_converter.convert(weather())
            logger.debug(f"In weather status {weather_response.status}")
            if weather_response.status == WeatherStatus.WEATHER_STATUS_DANGER or (
                Config.getRequiredBoolean("block_on_unspecified", "weather") and 
                weather_response.status == WeatherStatus.WEATHER_STATUS_UNSPECIFIED
            ):
                logger.info(f"In status danger or unspecified {weather_response.status}")
                mediator.is_disabled = True
                self._next_handler = None
        return super().handle(mediator)

class RoofTelescopeHandler(AbstractButtonHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if (
            mediator.status is RoofStatus.ROOF_OPENED and
            not self.__telescope_is_secure()
        ):
            self._next_handler = None
            mediator.is_disabled = True
            
        return super().handle(mediator)

    def __telescope_is_secure(self):
        return (
            telescope().status <= TelescopeStatus.SECURE and
            telescope().polling
        )

class RoofCurtainsHandler(AbstractButtonHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if (
            mediator.status is RoofStatus.ROOF_OPENED and
            not self.__curtains_are_secure()
        ):
            self._next_handler = None
            mediator.is_disabled = True

        return super().handle(mediator)

    def __curtains_are_secure(self):
        return (
            curtain_east().get_status() is CurtainStatus.CURTAIN_DISABLED and 
            curtain_west().get_status() is CurtainStatus.CURTAIN_DISABLED
        )

class RoofHandler(AbstractButtonHandler):
    def handle(self, mediator: RoofMediator) -> RoofResponse:
        if mediator.status in [RoofStatus.ROOF_OPENING, RoofStatus.ROOF_CLOSING]:
            self._next_handler = None
            mediator.is_disabled = True
        elif mediator.action is RoofAction.OPEN:
            loop = asyncio.get_event_loop()
            loop.create_task(mediator.button.open())
        elif mediator.action is RoofAction.CLOSE:
            loop = asyncio.get_event_loop()
            loop.create_task(mediator.button.close())

        return super().handle(mediator)
