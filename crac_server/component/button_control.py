import threading
from crac_protobuf.button_pb2 import ButtonStatus
from crac_server.config import Config
from gpiozero import OutputDevice


lock = threading.Lock()


class ButtonControl():
    def __init__(self, pin: int):
        self.output = OutputDevice(pin)
        self.lock = threading.Lock()

    def on(self):
        with self.lock:
            self.output.on()

    def off(self):
        with self.lock:
            self.output.off()

    def get_status(self) -> ButtonStatus:
        if self.output.value:
            return ButtonStatus.ON
        else:
            return ButtonStatus.OFF

SWITCHES = {
    "TELE_SWITCH": ButtonControl(Config.getInt("switch_power", "panel_board")),
    "CCD_SWITCH": ButtonControl(Config.getInt("switch_aux", "panel_board")),
    "FLAT_LIGHT": ButtonControl(Config.getInt("switch_panel", "panel_board")),
    "DOME_LIGHT": ButtonControl(Config.getInt("switch_light", "panel_board")),
}