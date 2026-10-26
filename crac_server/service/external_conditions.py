from functools import lru_cache
import logging
from time import monotonic
from typing import NamedTuple

from crac_protobuf.chart_pb2 import WeatherStatus  # type: ignore
from crac_protobuf.emergency_closure_pb2 import EmergencyClosureTrigger  # type: ignore
from crac_protobuf.roof_pb2 import RoofStatus  # type: ignore
from crac_protobuf.ups_pb2 import UpsStatus  # type: ignore

from crac_server.component.roof import roof
from crac_server.component.weather import weather
from crac_server.config import Config
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.service.emergency_closure import emergency_closure
from crac_server.service.ups_service import ups_service
from crac_server.status_log import ErrorCause, StatusLogger


logger = logging.getLogger(__name__)

WEATHER_UNAVAILABLE = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER_UNAVAILABLE
UPS_UNAVAILABLE = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_UPS_UNAVAILABLE


class UnavailableSource(NamedTuple):
    section: str
    wait_key: str


GOOD_READINGS_BEFORE_CLEAR = 3

UNAVAILABLE_SOURCES = {
    WEATHER_UNAVAILABLE: UnavailableSource(section="weather", wait_key="close_on_unspecified_after"),
    UPS_UNAVAILABLE: UnavailableSource(section="ups_emergency", wait_key="close_on_unspecified_after"),
}


class ExternalConditions:
    """The one answer to whether the world outside the dome lets the
    observatory operate: each component asks here, and each source is added
    here, so a new source cannot cover two components out of three."""

    def __init__(self) -> None:
        self._missing_since = {}
        self._good_readings = {}
        self._gate_log = StatusLogger(logger, "External conditions")

    def operation_blocked(self) -> bool:
        return self._weather_blocks() or self._ups_blocks()

    def _weather_blocks(self) -> bool:
        """A weather that cannot be read cannot say the operation is
        safe: it counts as unknown, never as an error on the button."""
        try:
            status = WeatherConverter().convert(weather()).status
        except Exception as e:
            self._gate_log.record("cannot read the weather", ErrorCause.DEVICE_UNREACHABLE, detail=str(e), exc_info=e)
            status = WeatherStatus.WEATHER_STATUS_UNSPECIFIED
        blocked = status == WeatherStatus.WEATHER_STATUS_DANGER or (
            status == WeatherStatus.WEATHER_STATUS_UNSPECIFIED and
            Config.getRequiredBoolean("block_on_unspecified", "weather")
        )
        if blocked:
            logger.info("The weather blocks the operation: %s", WeatherStatus.Name(status))
        return blocked

    def _ups_blocks(self) -> bool:
        """The status of the last check of the watch: a command never
        waits for the UPS to answer. A check that never ran counts as
        unknown, and unknown blocks when configured to."""
        try:
            status = ups_service().cached_status()
        except Exception as e:
            self._gate_log.record("cannot read the UPS", ErrorCause.DEVICE_UNREACHABLE, detail=str(e), exc_info=e)
            status = UpsStatus.UPS_STATUS_UNSPECIFIED
        blocked = status == UpsStatus.UPS_STATUS_DANGER or (
            status == UpsStatus.UPS_STATUS_UNSPECIFIED and
            Config.getRequiredBoolean("block_on_unspecified", "ups_emergency")
        )
        if blocked:
            logger.info("The UPS blocks the operation: %s", UpsStatus.Name(status))
        return blocked

    def note_availability(self, trigger: EmergencyClosureTrigger, available: bool) -> None:
        """Each source tells here on every check whether its data is fresh:
        unknown past its wait it starts the closure, and it gets the green
        light back only after three good readings in a row."""
        if available:
            good = self._good_readings.get(trigger, 0) + 1
            if good < GOOD_READINGS_BEFORE_CLEAR:
                self._good_readings[trigger] = good
                return
            self._good_readings.pop(trigger, None)
            self._missing_since.pop(trigger, None)
            emergency_closure().report(trigger, False)
            return
        self._good_readings.pop(trigger, None)
        if roof().get_status() == RoofStatus.ROOF_CLOSED:
            self._missing_since.pop(trigger, None)
            return
        source = UNAVAILABLE_SOURCES[trigger]
        since = self._missing_since.setdefault(trigger, monotonic())
        if monotonic() - since >= Config.getRequiredFloat(source.wait_key, source.section):
            emergency_closure().report(trigger, True)


@lru_cache(maxsize=1)
def external_conditions() -> ExternalConditions:
    return ExternalConditions()
