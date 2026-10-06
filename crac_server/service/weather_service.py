import asyncio
import logging
import math
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
from crac_protobuf.roof_pb2 import (
    RoofStatus,  # type: ignore
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
from crac_server.config import Config
from crac_server.converter.chart_builder import UnreachableThresholdError
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.status_log import ErrorCause, StatusLogger


logger = logging.getLogger(__name__)

MIN_CHECK_INTERVAL = 30


class WeatherService(WeatherServicer):

    def __init__(self) -> None:
        self.check_interval = self._check_interval()
        self.t = None
        super().__init__()
        self.lock = Lock()
        self.weather_converter = WeatherConverter()
        self._watch_log = StatusLogger(logger, "Weather watch")
        self._read_log = StatusLogger(logger, "Weather", WeatherStatus)

    @staticmethod
    def _check_interval() -> float:
        """A shorter interval would only spin the loop: the weather source
        itself refreshes far less often. NaN and infinity would silently stop
        the checks."""
        interval = Config.getRequiredFloat("check_interval", "weather")
        if not MIN_CHECK_INTERVAL <= interval < math.inf:
            raise ValueError(
                f"weather.check_interval must be a number of seconds, at least {MIN_CHECK_INTERVAL}: {interval}"
            )
        return interval

    async def GetStatus(self, request: WeatherRequest, context) -> WeatherResponse:
        return await self.check()

    async def watch(self):
        """Check the weather every check_interval seconds, for as long as the
        server runs, so that the closure does not wait for a client to ask.
        A failed check is logged, once per kind of failure, and the next one
        runs anyway."""
        logger.info("Weather watch: checking every %s seconds", self.check_interval)
        while True:
            try:
                await self.check()
                self._watch_log.record("running")
            except Exception as e:
                self._watch_log.record(
                    f"check failed: {type(e).__name__}", ErrorCause.UNEXPECTED_FAILURE, detail=str(e), exc_info=e,
                )
            await asyncio.sleep(self.check_interval)

    def _record_read_failure(self, detail: str, exc_info=None):
        """A failed refresh and the stale readings after it are one failure,
        recovered only when fresh data arrives."""
        self._read_log.record(
            WeatherStatus.WEATHER_STATUS_UNSPECIFIED, ErrorCause.DEVICE_UNREACHABLE, detail=detail, exc_info=exc_info,
        )

    async def check(self) -> WeatherResponse:
        """Read the weather and, when it is dangerous and the roof may be
        open, start the emergency closure unless one is already running."""
        try:
            response = await asyncio.to_thread(self.weather_converter.convert, weather())
        except UnreachableThresholdError:
            raise
        except Exception as e:
            response = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_UNSPECIFIED)
            self._record_read_failure(f"{type(e).__name__}: {e}", exc_info=e)
        else:
            if weather().is_expired():
                self._record_read_failure("no fresh weather data, using the last reading")
            else:
                self._read_log.record(response.status)
        logger.debug("weather response")
        logger.debug(response)

        if (
            response.status == WeatherStatus.WEATHER_STATUS_DANGER and
            roof().get_status() != RoofStatus.ROOF_CLOSED and
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
