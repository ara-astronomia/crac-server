import asyncio
from crac_server.component.roof.roof_control import RoofControl
from threading import Thread
from time import sleep


class MockRoofControl(RoofControl):

    def __init__(self):
        super().__init__()
        self.roof_open_switch.pin.drive_high()
        self.roof_closed_switch.pin.drive_low()

    async def open(self):
        self.roof_open_switch.pin.drive_high()
        self.roof_closed_switch.pin.drive_high()
        tstart = asyncio.to_thread(self.__wait_for_open__, self.roof_open_switch.pin)
        await tstart
        await super().open()

    async def close(self):
        self.roof_open_switch.pin.drive_high()
        self.roof_closed_switch.pin.drive_high()
        tstart = asyncio.to_thread(self.__wait_for_open__, self.roof_closed_switch.pin)
        await tstart
        await super().close()

    def __wait_for_open__(self, pin):
        sleep(10)
        pin.drive_low()
