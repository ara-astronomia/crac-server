import asyncio
from functools import lru_cache
import logging
from threading import Lock
from time import time

from crac_protobuf.button_pb2 import ButtonType  # type: ignore
from crac_protobuf.curtains_pb2 import CurtainStatus  # type: ignore
from crac_protobuf.emergency_closure_pb2 import (
    EmergencyClosure,  # type: ignore
    EmergencyClosureBlockReason,  # type: ignore
    EmergencyClosureStatus,  # type: ignore
    EmergencyClosureTrigger,  # type: ignore
)
from crac_protobuf.roof_pb2 import RoofStatus  # type: ignore
from crac_protobuf.telescope_pb2 import TelescopeStatus  # type: ignore

from crac_server.component.button_control import switches
from crac_server.component.curtains.factory_curtain import curtain_east, curtain_west
from crac_server.component.roof import roof
from crac_server.component.telescope import telescope
from crac_server.config import Config
from crac_server.status_log import ErrorCause, StatusLogger


logger = logging.getLogger(__name__)

WAIT_STEP = 0.1
TELESCOPE_STATUSES_FROM_COORDINATES = range(TelescopeStatus.PARKED, TelescopeStatus.NORTHWEST + 1)
TELESCOPE_FAILURES = (TelescopeStatus.LOST, TelescopeStatus.ERROR)
CAUSE_BY_BLOCK_REASON = {
    EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN: ErrorCause.DEVICE_UNREACHABLE,
    EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_PARK_NOT_REACHED: ErrorCause.MOVEMENT_NOT_CONFIRMED,
    EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_CURTAINS_NOT_DISABLED: ErrorCause.MOVEMENT_NOT_CONFIRMED,
    EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_ROOF_NOT_CLOSED: ErrorCause.MOVEMENT_NOT_CONFIRMED,
    EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_INTERNAL_ERROR: ErrorCause.UNEXPECTED_FAILURE,
}


class EmergencyBlock(Exception):

    def __init__(self, reason: EmergencyClosureBlockReason) -> None:
        super().__init__(EmergencyClosureBlockReason.Name(reason))
        self.reason = reason


class EmergencyClosureProcedure:
    """The one procedure that parks the telescope, lowers the curtains and
    closes the roof, whatever made it necessary. It never moves the roof
    while the telescope position is unknown or not safe."""

    def __init__(self) -> None:
        self.park_timeout = Config.getRequiredFloat("park_timeout", "emergency_closure")
        self.curtains_timeout = Config.getRequiredFloat("curtains_timeout", "emergency_closure")
        self.max_reading_age = Config.getRequiredFloat("max_reading_age", "emergency_closure")
        self._lock = Lock()
        self._status = EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_IDLE
        self._block_reason = EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_UNSPECIFIED
        self._status_since = int(time())
        self._triggers = []
        self._critical = set()
        self._task = None
        self._log = StatusLogger(logger, "Emergency closure", EmergencyClosureStatus)

    def report(self, trigger, critical: bool) -> None:
        """Called by each trigger source on every check, from the event loop:
        starts, resumes or settles the closure. No await in here, so two
        sources can never start two closures."""
        if critical:
            self._critical.add(trigger)
            if trigger not in self._triggers:
                self._triggers.append(trigger)
        else:
            self._critical.discard(trigger)

        if self._task is not None and not self._task.done():
            return
        if not self._critical:
            self._triggers = []
            self._set(EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_IDLE)
        elif roof().get_status() == RoofStatus.ROOF_CLOSED:
            self._set(EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_COMPLETED)
        elif self._status != EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_BLOCKED:
            self._start()
        elif self._block_reason == EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN:
            telescope().polling_start()
            if self._telescope_readable():
                self._start()

    def state(self) -> EmergencyClosure:
        with self._lock:
            return EmergencyClosure(
                status=self._status,
                triggers=self._triggers,
                block_reason=self._block_reason,
                status_since=self._status_since,
            )

    def _start(self) -> None:
        logger.info(
            "Emergency closure started, triggers: %s",
            ", ".join(EmergencyClosureTrigger.Name(trigger) for trigger in self._triggers),
        )
        self._set(EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_IN_PROGRESS)
        self._task = asyncio.get_running_loop().create_task(self._close())

    async def _close(self) -> None:
        try:
            await self._park_telescope()
            await self._lower_curtains()
            if not await roof().close():
                raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_ROOF_NOT_CLOSED)
            await asyncio.to_thread(telescope().polling_end)
            switches()[ButtonType.Name(ButtonType.TELE_SWITCH)].off()
            logger.info("Emergency closure completed")
            self._set(EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_COMPLETED)
        except EmergencyBlock as block:
            self._set(EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_BLOCKED, block.reason)
        except Exception as e:
            self._set(
                EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_BLOCKED,
                EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_INTERNAL_ERROR,
                exc_info=e,
            )

    async def _park_telescope(self) -> None:
        telescope().polling_start()
        await self._wait_until(self._telescope_readable_or_failed, self.max_reading_age)
        if not self._telescope_readable():
            raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
        if telescope().status <= TelescopeStatus.SECURE:
            return
        telescope().queue_park()
        await self._wait_until(self._telescope_safe_or_unreadable, self.park_timeout)
        if not self._telescope_readable():
            raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
        if telescope().status > TelescopeStatus.SECURE:
            raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_PARK_NOT_REACHED)

    def _telescope_readable_or_failed(self) -> bool:
        return self._telescope_readable() or telescope().status in TELESCOPE_FAILURES

    def _telescope_safe_or_unreadable(self) -> bool:
        return not self._telescope_readable() or telescope().status <= TelescopeStatus.SECURE

    async def _lower_curtains(self) -> None:
        curtain_east().disable()
        curtain_west().disable()
        if not await self._wait_until(self._curtains_disabled, self.curtains_timeout):
            raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_CURTAINS_NOT_DISABLED)

    @staticmethod
    def _curtains_disabled() -> bool:
        return all(curtain().get_status() == CurtainStatus.CURTAIN_DISABLED for curtain in (curtain_east, curtain_west))

    def _telescope_readable(self) -> bool:
        """Coordinates read from the mount, in range, recent enough, and a
        status that comes from them."""
        mount = telescope()
        coords = mount.aa_coords
        return (
            coords is not None and
            -90 <= coords.alt <= 90 and
            0 <= coords.az < 360 and
            mount.status in TELESCOPE_STATUSES_FROM_COORDINATES and
            mount.seconds_since_last_reading() <= self.max_reading_age
        )

    @staticmethod
    async def _wait_until(condition, timeout: float) -> bool:
        """True as soon as condition holds, False if it still does not after
        timeout seconds."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not condition():
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(WAIT_STEP)
        return True

    def _set(self, status, block_reason=EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_UNSPECIFIED, exc_info=None) -> None:
        with self._lock:
            if status != self._status:
                self._status_since = int(time())
            self._status = status
            self._block_reason = block_reason
        self._log.record(
            status,
            CAUSE_BY_BLOCK_REASON.get(block_reason),
            detail=EmergencyClosureBlockReason.Name(block_reason) if block_reason else None,
            exc_info=exc_info,
        )


@lru_cache(maxsize=1)
def emergency_closure() -> EmergencyClosureProcedure:
    return EmergencyClosureProcedure()
