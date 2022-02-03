from gpiozero import OutputDevice

from crac_protobuf.button_pb2 import ButtonStatus


class ButtonControl():
    def __init__(self, pin):
        self.output = OutputDevice(pin)

    def on(self):
        self.output.on()
        return ButtonStatus.ON

    def off(self):
        self.output.off()
        return ButtonStatus.OFF

    def read(self):
        if self.output.value:
            return ButtonStatus.ON
        else:
            return ButtonStatus.OFF
