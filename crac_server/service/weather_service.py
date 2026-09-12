import asyncio
import logging
from threading import Lock, Thread
from time import sleep
from crac_protobuf.button_pb2 import (
    ButtonType,  # type: ignore
)
from crac_protobuf.chart_pb2_grpc import WeatherServicer
from crac_protobuf.chart_pb2 import (
    WeatherRequest,  # type: ignore
    WeatherResponse,  # type: ignore
    WeatherStatus,  # type: ignore
)
from crac_protobuf.curtains_pb2 import (
    CurtainStatus,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeSpeed,  # type: ignore
    TelescopeStatus,  # type: ignore
)
from crac_server.component.button_control import switches
from crac_server.component.curtains.factory_curtain import curtain_east, curtain_west
from crac_server.component.roof import roof
from crac_server.component.telescope import telescope
from crac_server.component.weather import weather
from crac_server.converter.chart_builder import UnreachableThresholdError
from crac_server.converter.weather_converter import WeatherConverter


logger = logging.getLogger(__name__)


class WeatherService(WeatherServicer):

    def __init__(self) -> None:
        self.t = None
        super().__init__()
        self.lock = Lock()
        self.weather_converter = WeatherConverter()

    async def GetStatus(self, request: WeatherRequest, context) -> WeatherResponse:
        try:
            response = await asyncio.to_thread(self.weather_converter.convert, weather())
        except UnreachableThresholdError:
            raise
        except Exception:
            logger.error("Weather read failed: reporting status as UNSPECIFIED", exc_info=1)
            response = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_UNSPECIFIED)
        logger.debug("weather response")
        logger.debug(response)

        if (
            response.status == WeatherStatus.WEATHER_STATUS_DANGER and
            telescope().polling and 
            self.t == None
        ):
            logger.info("weather in danger status - block crac")
            self.t = Thread(target=self._emergency_closure, args=(asyncio.get_running_loop(),))
            self.t.start()
        return response

    def _emergency_closure(self, loop: asyncio.AbstractEventLoop):
        """Close the observatory from its own thread.

        The roof is driven by a coroutine owned by the event loop, so its
        closure is handed over to the loop instead of being called here.
        """
        try:
            self._close_crac(loop)
        except Exception:
            logger.error("weather in danger status - the closure did not complete", exc_info=True)
        finally:
            self.t = None

    def _close_crac(self, loop: asyncio.AbstractEventLoop):
        with self.lock:
            logger.info("weather in danger status - send telescope in park")
            telescope().queue_park()
            
            while telescope().status > TelescopeStatus.SECURE:
                logger.info("weather in danger status - waiting for telescope in park")
                sleep(1)
            logger.info(f"weather in danger status - telescope is in status {telescope().status}")
            
            while curtain_east().get_status() in (CurtainStatus.CURTAIN_OPENING, CurtainStatus.CURTAIN_CLOSING):
                sleep(1)
                logger.info(f"weather in danger status - curtain east is in status {curtain_east().get_status()}")
            logger.info("weather in danger status - disable east curt")
            curtain_east().disable()
        
            while curtain_west().get_status() in (CurtainStatus.CURTAIN_OPENING, CurtainStatus.CURTAIN_CLOSING):
                sleep(1)
                logger.info(f"weather in danger status - curtain west is in status {curtain_west().get_status()}")
            logger.info("weather in danger status - disable west curt")
            curtain_west().disable()
            
            while (
                curtain_east().get_status() is not CurtainStatus.CURTAIN_DISABLED or 
                curtain_west().get_status() is not CurtainStatus.CURTAIN_DISABLED
            ):
                sleep(1)
            logger.info("weather in danger status - close the roof")
            if asyncio.run_coroutine_threadsafe(roof().close(), loop).result():
                logger.info("weather in danger status - the roof is closed")
            else:
                logger.error("weather in danger status - the roof did not close")

            logger.info("weather in danger status - switch off telescope button")
            telescope().polling_end()
            switches()[ButtonType.Name(ButtonType.TELE_SWITCH)].off()
