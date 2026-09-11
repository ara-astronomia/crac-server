import asyncio
import logging
from gpiozero import OutputDevice, DigitalInputDevice
from crac_server.config import Config
from crac_protobuf.roof_pb2 import RoofStatus
from crac_server.status_log import ErrorCause, StatusLogger


logger = logging.getLogger(__name__)

class RoofControl():

    def __init__(self):
        self.motor = OutputDevice(Config.getInt("switch_roof", "roof_board"))
        self.roof_closed_switch = DigitalInputDevice(Config.getInt("roof_verify_closed", "roof_board"), pull_up=True)
        self.roof_open_switch = DigitalInputDevice(Config.getInt("roof_verify_open", "roof_board"), pull_up=True)
        self.timeout = Config.getInt("roof_timeout", "roof_board")
        self.lock = asyncio.Lock()
        self.movement_not_confirmed = False
        self._status_log = StatusLogger(logger, "Roof", RoofStatus)

    async def open(self):
        async with self.lock:
            self.motor.on()
            is_open = await self.__reaches(self.roof_open_switch)
            self.movement_not_confirmed = not is_open
        if not is_open:
            logger.error(
                "Roof opening not confirmed after %s seconds: motor=%s, "
                "open limit switch=%s, closed limit switch=%s",
                self.timeout, self.motor.value,
                self.roof_open_switch.is_active, self.roof_closed_switch.is_active
            )
            await self.close()
        return is_open

    async def close(self):
        async with self.lock:
            self.motor.off()
            is_closed = await self.__reaches(self.roof_closed_switch)
            self.movement_not_confirmed = not is_closed
            if not is_closed:
                logger.error(
                    "Roof closing not confirmed after %s seconds: motor=%s, "
                    "closed limit switch=%s, open limit switch=%s",
                    self.timeout, self.motor.value,
                    self.roof_closed_switch.is_active, self.roof_open_switch.is_active
                )
            return is_closed

    async def __reaches(self, limit_switch) -> bool:
        """Waits off the event loop, so the server keeps answering for the
        whole run. A cancelled wait leaves the motor driving and the roof
        mid travel, which only the log can tell afterwards."""
        try:
            return await asyncio.to_thread(limit_switch.wait_for_active, self.timeout)
        except asyncio.CancelledError:
            logger.error("Roof run interrupted with the motor still driving: the roof is left mid travel")
            raise

    def get_status(self) -> RoofStatus:
        is_roof_closed = self.roof_closed_switch.is_active
        logger.debug(f'roof closed switch is {is_roof_closed}')
        is_roof_open = self.roof_open_switch.is_active
        logger.debug(f'roof opened switch is {is_roof_open}')
        is_switched_on = self.motor.value
        logger.debug(f'roof motor switch is {is_switched_on}')

        if is_roof_closed and is_roof_open:
            status = RoofStatus.ROOF_ERROR
            self._status_log.record(
                status, ErrorCause.SENSORS_INCONSISTENT,
                detail="both limit switches active",
            )
        elif self.movement_not_confirmed:
            status = RoofStatus.ROOF_ERROR
            self._status_log.record(
                status, ErrorCause.MOVEMENT_NOT_CONFIRMED,
                detail=f"no limit switch after {self.timeout}s",
            )
        elif is_roof_closed and not is_switched_on:
            status = RoofStatus.ROOF_CLOSED
        elif is_roof_open and is_switched_on:
            status = RoofStatus.ROOF_OPENED
        elif is_switched_on:
            status = RoofStatus.ROOF_OPENING
        else:
            status = RoofStatus.ROOF_CLOSING

        logger.debug(f'roof status is {status}')
        if status is not RoofStatus.ROOF_ERROR:
            self._status_log.record(status)
        return status
