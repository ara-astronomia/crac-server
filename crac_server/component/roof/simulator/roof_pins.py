from threading import Timer
from gpiozero import Device
from gpiozero.pins.mock import MockPin
from crac_server.component.roof.roof_control import RoofControl
from crac_server.config import Config


TRAVEL_SECONDS = 10


class MockRoofMotorPin(MockPin):
    """Motor pin wired to the limit switches it drives.

    A mock limit switch is never tripped by anything, so a roof built on plain
    mock pins would run until its timeout and report itself blocked. Here the
    motor leaves both switches free while the roof travels and latches the one
    at the end it is heading to, the way the real wiring does.
    """

    open_switch = None
    closed_switch = None
    travel_seconds = TRAVEL_SECONDS

    def __init__(self, factory, info, open_switch=None, closed_switch=None,
                 travel_seconds=TRAVEL_SECONDS):
        super().__init__(factory, info)
        self.open_switch = open_switch
        self.closed_switch = closed_switch
        self.travel_seconds = travel_seconds
        self._travel = None

    def _set_state(self, value):
        is_a_new_run = self.state != bool(value)
        super()._set_state(value)
        if not is_a_new_run or self.open_switch is None:
            return
        if self._travel:
            self._travel.cancel()
        self.open_switch.drive_high()
        self.closed_switch.drive_high()
        arriving_at = self.open_switch if value else self.closed_switch
        self._travel = Timer(self.travel_seconds, arriving_at.drive_low)
        self._travel.start()


def simulated_roof(travel_seconds: float = TRAVEL_SECONDS) -> RoofControl:
    """The production RoofControl with only the travel of the roof simulated,
    starting from a closed roof."""
    factory = Device.pin_factory
    open_switch = factory.pin(Config.getInt("roof_verify_open", "roof_board"))
    closed_switch = factory.pin(Config.getInt("roof_verify_closed", "roof_board"))
    factory.pin(
        Config.getInt("switch_roof", "roof_board"),
        pin_class=MockRoofMotorPin,
        open_switch=open_switch,
        closed_switch=closed_switch,
        travel_seconds=travel_seconds,
    )
    roof_control = RoofControl()
    roof_control.roof_closed_switch.pin.drive_low()
    return roof_control
