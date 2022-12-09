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
        t = Thread(
            target=self.__wait_for_open__,
            args=(self.roof_open_switch.pin,)
        )
        t.start()
        await super().open()
        t.join()

    async def close(self):
        self.roof_open_switch.pin.drive_high()
        self.roof_closed_switch.pin.drive_high()
        t = Thread(
            target=self.__wait_for_open__,
            args=(self.roof_closed_switch.pin,)
        )
        t.start()
        await super().close()
        t.join()

    def __wait_for_open__(self, pin):
        sleep(10)
        pin.drive_low()
