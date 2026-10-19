from functools import lru_cache
import logging
from time import monotonic
from typing import NamedTuple

from crac_protobuf.chart_pb2 import WeatherStatus  # type: ignore
from crac_protobuf.emergency_closure_pb2 import EmergencyClosureTrigger  # type: ignore
from crac_protobuf.roof_pb2 import RoofStatus  # type: ignore

from crac_server.component.roof import roof
from crac_server.component.weather import weather
from crac_server.config import Config
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.service.emergency_closure import emergency_closure


logger = logging.getLogger(__name__)

WEATHER_UNAVAILABLE = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER_UNAVAILABLE


class UnavailableSource(NamedTuple):
    section: str
    wait_key: str


UNAVAILABLE_SOURCES = {
    WEATHER_UNAVAILABLE: UnavailableSource(section="weather", wait_key="close_on_unspecified_after"),
}


class ExternalConditions:
    """The one answer to whether the world outside the dome lets the
    observatory operate: each component asks here, and each source is added
    here, so a new source cannot cover two components out of three."""

    def __init__(self) -> None:
        self._missing_since = {}

    def operation_blocked(self) -> bool:
        status = WeatherConverter().convert(weather()).status
        blocked = status == WeatherStatus.WEATHER_STATUS_DANGER or (
            status == WeatherStatus.WEATHER_STATUS_UNSPECIFIED and
            Config.getRequiredBoolean("block_on_unspecified", "weather")
        )
        if blocked:
            logger.info("The weather blocks the operation: %s", WeatherStatus.Name(status))
        return blocked

    def note_availability(self, trigger: EmergencyClosureTrigger, available: bool) -> None:
        """Each source tells here on every check whether its data is fresh: a
        source unknown longer than its configured wait, with the roof not
        closed, starts the emergency closure."""
        if available:
            self._missing_since.pop(trigger, None)
            emergency_closure().report(trigger, False)
            return
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
