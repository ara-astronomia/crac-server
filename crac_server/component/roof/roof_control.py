import asyncio
import logging
from gpiozero import OutputDevice, DigitalInputDevice
from crac_server.config import Config
from crac_protobuf.roof_pb2 import RoofStatus


logger = logging.getLogger(__name__)

class RoofControl():

    def __init__(self):
        self.motor = OutputDevice(Config.getInt("switch_roof", "roof_board"))
        self.roof_closed_switch = DigitalInputDevice(Config.getInt("roof_verify_closed", "roof_board"), pull_up=True)
        self.roof_open_switch = DigitalInputDevice(Config.getInt("roof_verify_open", "roof_board"), pull_up=True)
        self.timeout = Config.getInt("roof_timeout", "roof_board")
        self.lock = asyncio.Lock()
        self.is_blocked = False

    async def open(self):
        async with self.lock:
            self.motor.on()
            self.is_blocked = not self.roof_open_switch.wait_for_active(self.timeout)
        if self.is_blocked:
            await self.close()
            print(self.motor.value)
            print(self.roof_open_switch.is_active)
            print(self.roof_closed_switch.is_active)
        return not self.is_blocked

    async def close(self):
        async with self.lock:
            self.motor.off()
            self.is_blocked = not self.roof_closed_switch.wait_for_active(self.timeout)
            return not self.is_blocked

    def get_status(self) -> RoofStatus:
        is_roof_closed = self.roof_closed_switch.is_active
        logger.debug(f'roof closed switch is {is_roof_closed}')
        is_roof_open = self.roof_open_switch.is_active
        logger.debug(f'roof opened switch is {is_roof_open}')
        is_switched_on = self.motor.value
        logger.debug(f'roof motor switch is {is_switched_on}')

        if (is_roof_closed and is_roof_open) or self.is_blocked:
            status = RoofStatus.ROOF_ERROR
        elif is_roof_closed and not is_switched_on:
            status = RoofStatus.ROOF_CLOSED
        elif is_roof_open and is_switched_on:
            status = RoofStatus.ROOF_OPENED
        elif is_switched_on:
            status = RoofStatus.ROOF_OPENING
        else:
            status = RoofStatus.ROOF_CLOSING

        logger.debug(f'roof status is {status}')
        return status
