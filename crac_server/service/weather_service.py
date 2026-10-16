import asyncio
import logging
import math
from crac_protobuf.chart_pb2_grpc import WeatherServicer
from crac_protobuf.chart_pb2 import (
    WeatherRequest,  # type: ignore
    WeatherResponse,  # type: ignore
    WeatherStatus,  # type: ignore
)
from crac_protobuf.emergency_closure_pb2 import (
    EmergencyClosureTrigger,  # type: ignore
)
from crac_server.component.weather import weather
from crac_server.config import Config
from crac_server.converter.chart_builder import UnreachableThresholdError
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.service.emergency_closure import emergency_closure
from crac_server.status_log import ErrorCause, StatusLogger


logger = logging.getLogger(__name__)

MIN_CHECK_INTERVAL = 30
WEATHER = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER


class WeatherService(WeatherServicer):

    def __init__(self) -> None:
        self.check_interval = self._check_interval()
        super().__init__()
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
        """Read the weather and report it to the emergency closure. An unknown
        weather reports nothing: it neither starts nor settles a closure."""
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

        if response.status != WeatherStatus.WEATHER_STATUS_UNSPECIFIED:
            emergency_closure().report(WEATHER, response.status == WeatherStatus.WEATHER_STATUS_DANGER)
        response.emergency_closure.CopyFrom(emergency_closure().state())
        return response
