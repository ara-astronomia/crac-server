from threading import Timer
from gpiozero import Device
from gpiozero.pins.mock import MockPin
from crac_server.component.roof.roof_control import RoofControl
from crac_server.config import Config


TRAVEL_SECONDS = 10


class MockRoofMotorPin(MockPin):
    """Motor pin wired to the limit switches it drives.

    A mock limit switch is never tripped by anything, so a roof built on plain
    mock pins would run until its timeout and never confirm the movement. Here
    the motor leaves both switches free while the roof travels and latches the
    one at the end it is heading to, the way the real wiring does.
    """

    def __init__(self, factory, info, open_switch=None, closed_switch=None,
                 travel_seconds=TRAVEL_SECONDS):
        super().__init__(factory, info)
        self.open_switch = open_switch
        self.closed_switch = closed_switch
        self.travel_seconds = travel_seconds

    def _set_state(self, value):
        heading_open = bool(value)
        is_a_new_run = self.state != heading_open
        super()._set_state(value)
        if not is_a_new_run or self.open_switch is None or self.closed_switch is None:
            return
        self.open_switch.drive_high()
        self.closed_switch.drive_high()
        arriving_at = self.open_switch if heading_open else self.closed_switch

        def reach_the_limit_switch():
            """The motor can reverse while the roof travels: latch the switch
            only if it is still heading this way."""
            if self.state == heading_open:
                arriving_at.drive_low()

        travel = Timer(self.travel_seconds, reach_the_limit_switch)
        travel.daemon = True
        travel.start()


def simulated_roof(travel_seconds: float = TRAVEL_SECONDS) -> RoofControl:
    """The production RoofControl with only the travel of the roof simulated,
    starting from a closed roof."""
    factory = Device.pin_factory
    open_switch = factory.pin(Config.getInt("roof_verify_open", "roof_board"))
    closed_switch = factory.pin(Config.getInt("roof_verify_closed", "roof_board"))
    motor = factory.pin(
        Config.getInt("switch_roof", "roof_board"),
        pin_class=MockRoofMotorPin,
        open_switch=open_switch,
        closed_switch=closed_switch,
        travel_seconds=travel_seconds,
    )
    if not isinstance(motor, MockRoofMotorPin):
        raise RuntimeError(
            f"{motor!r} was already reserved as a plain mock pin, so the roof "
            "is not wired to its limit switches and would never reach one"
        )
    roof_control = RoofControl()
    roof_control.roof_closed_switch.pin.drive_low()
    return roof_control
