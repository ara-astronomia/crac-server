from gpiozero import OutputDevice

from crac_protobuf.button_pb2 import ButtonStatus

from crac_server.config import Config


class ButtonControl():
    def __init__(self, pin):
        self.output = OutputDevice(pin)

    def on(self):
        self.output.on()

    def off(self):
        self.output.off()

    def get_status(self):
        if self.output.value:
            return ButtonStatus.ON
        else:
            return ButtonStatus.OFF


TELE_SWITCH = ButtonControl(Config.getInt("switch_power", "panel_board"))
CCD_SWITCH = ButtonControl(Config.getInt("switch_aux", "panel_board"))
FLAT_LIGHT = ButtonControl(Config.getInt("switch_panel", "panel_board"))
DOME_LIGHT = ButtonControl(Config.getInt("switch_light", "panel_board"))