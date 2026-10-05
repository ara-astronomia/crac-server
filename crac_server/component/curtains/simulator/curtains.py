from crac_server.component.curtains.curtains import BOTTOM_STEP, Curtain
from threading import Thread
from time import sleep


class MockCurtain(Curtain):
    """Starts on its closed switch, and turns its encoder while the motor runs."""

    def __init__(self, encoder: dict[str, int], closed_switch: dict[str, int], open_switch: dict[str, int], motor: dict[str, int], orientation: str):
        self._thread = None
        self._generation = 0
        super().__init__(encoder, closed_switch, open_switch, motor, orientation)
        self._closed_switch.pin.drive_low()
        self._open_switch.pin.drive_high()

    def _start(self, direction: int):
        """Every start gets its own thread: the previous one sees a newer
        generation and leaves, even if it was already on its way out."""
        super()._start(direction)
        self._generation += 1
        self._thread = Thread(
            target=self._fake_move, args=(direction, self._generation),
            name=f"simulated-motor-{self._orientation}", daemon=True,
        )
        self._thread.start()

    def _fake_move(self, direction: int, generation: int):
        pins = (self._encoder.a.pin, self._encoder.b.pin)
        while True:
            sleep(0.2)
            if self._motor.value != direction or generation != self._generation:
                return
            for pin in pins if direction == 1 else reversed(pins):
                pin.drive_low()
            for pin in pins if direction == 1 else reversed(pins):
                pin.drive_high()
            self._update_closed_switch()

    def _update_closed_switch(self):
        """Only the closed switch trips: the real curtains run out of travel
        before reaching the open switch."""
        if self.steps() <= BOTTOM_STEP + self._tolerance_steps:
            self._closed_switch.pin.drive_low()
        else:
            self._closed_switch.pin.drive_high()
