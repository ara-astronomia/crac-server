import asyncio
from functools import lru_cache
import logging
from threading import Lock
from time import monotonic, time

from crac_protobuf.curtains_pb2 import CurtainStatus  # type: ignore
from crac_protobuf.cover_mirror_pb2 import CoverMirrorStatus  # type: ignore
from crac_protobuf.emergency_closure_pb2 import (
    EmergencyClosure,  # type: ignore
    EmergencyClosureBlockReason,  # type: ignore
    EmergencyClosureStatus,  # type: ignore
    EmergencyClosureTrigger,  # type: ignore
)
from crac_protobuf.roof_pb2 import RoofStatus  # type: ignore
from crac_protobuf.telescope_pb2 import TelescopeSpeed, TelescopeStatus  # type: ignore

from crac_server.component.curtains.factory_curtain import curtain_east, curtain_west
from crac_server.component.cover_mirror import cover_mirror
from crac_server.component.roof import roof
from crac_server.component.telescope import telescope
from crac_server.config import Config
from crac_server.status_log import ErrorCause, StatusLogger


logger = logging.getLogger(__name__)

WAIT_STEP = 0.1
TELESCOPE_STATUSES_FROM_COORDINATES = range(TelescopeStatus.PARKED, TelescopeStatus.NORTHWEST + 1)
RETRIED_BLOCK_REASONS = (
    EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN,
    EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_PARK_NOT_REACHED,
)
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
        self._started_at = 0.0
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
        elif self._block_reason in RETRIED_BLOCK_REASONS:
            telescope().polling_start()
            if self._telescope_readable():
                self._start(retry=True)

    def state(self) -> EmergencyClosure:
        with self._lock:
            return EmergencyClosure(
                status=self._status,
                triggers=self._triggers,
                block_reason=self._block_reason,
                status_since=self._status_since,
            )

    def _start(self, retry: bool = False) -> None:
        """A retry stays BLOCKED while it runs, so a block that keeps coming
        back is logged once and keeps the time it first happened."""
        self._started_at = monotonic()
        if not retry:
            logger.info(
                "Emergency closure started, triggers: %s",
                ", ".join(EmergencyClosureTrigger.Name(trigger) for trigger in self._triggers),
            )
            self._set(EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_IN_PROGRESS)
        self._task = asyncio.get_running_loop().create_task(self._close())

    async def _close(self) -> None:
        try:
            await self._close_cover_mirror()
            await self._park_telescope()
            await self._lower_curtains()
            self._require_telescope_safe()
            if not await roof().close():
                raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_ROOF_NOT_CLOSED)
            await asyncio.to_thread(telescope().polling_end)
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

    async def _close_cover_mirror(self) -> None:
        """The petals move on their own servos, independent of the mount, so
        they are closed even when the telescope cannot be read. Best effort:
        a cover mirror that fails must not stop the roof from closing."""
        try:
            status = await asyncio.to_thread(cover_mirror().get_status)
            if status not in (CoverMirrorStatus.COVER_MIRROR_CLOSED, CoverMirrorStatus.COVER_MIRROR_CLOSING):
                await cover_mirror().close()
        except Exception:
            logger.warning("The cover mirror could not be closed", exc_info=True)

    async def _park_telescope(self) -> None:
        telescope().polling_start()
        await self._wait_until(self._telescope_read_or_failed, self.max_reading_age)
        if not self._telescope_read_since_start():
            raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
        if self._telescope_safe():
            return
        telescope().queue_park()
        await self._wait_until(self._telescope_safe_or_lost, self.park_timeout)
        self._require_telescope_safe()

    def _require_telescope_safe(self) -> None:
        if not self._telescope_read_since_start():
            raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
        if not self._telescope_safe():
            raise EmergencyBlock(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_PARK_NOT_REACHED)

    def _telescope_read_or_failed(self) -> bool:
        mount = telescope()
        failed = mount.status == TelescopeStatus.LOST or mount.status == TelescopeStatus.ERROR and not mount.movement_failed
        return self._telescope_read_since_start() or failed

    def _telescope_read_since_start(self) -> bool:
        """Readable, and read after the closure started: while a park or flat
        of crac runs the position is not read again, and the one from before
        would still look recent."""
        return (
            self._telescope_readable() and
            telescope().seconds_since_last_reading() <= monotonic() - self._started_at
        )

    def _telescope_safe_or_lost(self) -> bool:
        """Only LOST ends the wait early: a park that succeeds clears a failed
        movement a moment before the next reading replaces its ERROR."""
        return self._telescope_safe() or telescope().status == TelescopeStatus.LOST

    def _telescope_safe(self) -> bool:
        """Read since the start, not slewing and low enough for the roof: the
        PARKED switch turns true as soon as a park starts, and a parked mount
        can report its coordinates in Alert, so a speed in error is accepted."""
        mount = telescope()
        return (
            self._telescope_read_since_start() and
            mount.speed != TelescopeSpeed.SPEED_SLEWING and
            mount.aa_coords.alt <= Config.getFloat("max_secure_alt", "telescope")
        )

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
        status that comes from them, or the ERROR of a movement that failed."""
        mount = telescope()
        coords = mount.aa_coords
        return (
            coords is not None and
            -90 <= coords.alt <= 90 and
            0 <= coords.az < 360 and
            (mount.status in TELESCOPE_STATUSES_FROM_COORDINATES or
             mount.status == TelescopeStatus.ERROR and mount.movement_failed) and
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
