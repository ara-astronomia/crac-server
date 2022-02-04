from gpiozero import OutputDevice, DigitalInputDevice

from crac_server.config import Config
from crac_protobuf.roof_pb2 import RoofStatus


class RoofControl():

    def __init__(self):
        self.motor = OutputDevice(Config.getInt("switch_roof", "roof_board"))
        self.roof_closed_switch = DigitalInputDevice(Config.getInt("roof_verify_closed", "roof_board"), pull_up=True)
        self.roof_open_switch = DigitalInputDevice(Config.getInt("roof_verify_open", "roof_board"), pull_up=True)

    def open(self):
        self.motor.on()
        return self.roof_open_switch.wait_for_active()

    def close(self):
        self.motor.off()
        return self.roof_closed_switch.wait_for_active()

    def read(self):
        is_roof_closed = self.roof_closed_switch.is_active
        is_roof_open = self.roof_open_switch.is_active
        is_switched_on = self.motor.value

        if is_roof_closed and is_roof_open:
            return RoofStatus.ROOF_ERROR
        elif is_roof_closed and not is_switched_on:
            return RoofStatus.ROOF_CLOSED
        elif is_roof_open and is_switched_on:
            return RoofStatus.ROOF_OPENED
        elif is_switched_on:
            return RoofStatus.ROOF_OPENING
        else:
            return RoofStatus.ROOF_CLOSING
