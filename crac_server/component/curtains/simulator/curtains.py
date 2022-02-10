from threading import Thread
from time import sleep

from crac_server.component.curtains.curtains import Curtain


class MockCurtain(Curtain):

    def __init__(self, rotary_encoder, curtain_closed, curtain_open, motor):
        super().__init__(rotary_encoder, curtain_closed, curtain_open, motor)
        self.curtain_closed.pin.drive_low()
        self.curtain_open.pin.drive_high()

    def __rotate_cw__(self, *inputs):
        [input.pin.drive_low() for input in inputs if self.target is not None]
        [input.pin.drive_high() for input in inputs if self.target is not None]

    def __rotate_ccw__(self, *inputs):
        [input.pin.drive_low() for input in reversed(inputs) if self.target is not None]
        [input.pin.drive_high() for input in reversed(inputs) if self.target is not None]

    def __check_curtains_limit__(self):
        if self.steps() <= self.__min_step__:
            self.curtain_closed.pin.drive_low()
        else:
            self.curtain_closed.pin.drive_high()
        if self.steps() >= self.__max_step__:
            self.curtain_open.pin.drive_low()
        else:
            self.curtain_open.pin.drive_high()

    def __open__(self):
        super().__open__()
        self.t = Thread(target=self.__fake_move_forward__, args=(self,))
        self.t.start()

    def __close__(self):
        super().__close__()
        self.t = Thread(target=self.__fake_move_backward__, args=(self,))
        self.t.start()

    def __fake_move_forward__(self, curtain):
        while curtain.motor.is_active:
            sleep(0.2)
            curtain.__rotate_cw__(curtain.rotary_encoder.a, curtain.rotary_encoder.b)
            curtain.__check_curtains_limit__()

    def __fake_move_backward__(self, curtain):
        while curtain.motor.is_active:
            sleep(0.2)
            curtain.__rotate_ccw__(curtain.rotary_encoder.a, curtain.rotary_encoder.b)
            curtain.__check_curtains_limit__()
