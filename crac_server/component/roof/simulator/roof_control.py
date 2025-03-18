import asyncio
from crac_server.component.roof.roof_control import RoofControl


class MockRoofControl(RoofControl):

    def __init__(self):
        super().__init__()
        if self.roof_open_switch.pin:
            self.roof_open_switch.pin.drive_high()
        if self.roof_closed_switch.pin:
            self.roof_closed_switch.pin.drive_low()

    async def open(self):
        self.__movement_in_progress()
        open = super().open()
        await self.__wait_for_open__(self.roof_open_switch.pin)
        await open

    async def close(self):
        self.__movement_in_progress()
        close = super().close()
        await self.__wait_for_open__(self.roof_closed_switch.pin)
        await close

    async def __wait_for_open__(self, pin):
        await asyncio.sleep(10)
        pin.drive_low()

    def __movement_in_progress(self):
        if self.roof_open_switch.pin:
            self.roof_open_switch.pin.drive_high()
        if self.roof_closed_switch.pin:
            self.roof_closed_switch.pin.drive_high()