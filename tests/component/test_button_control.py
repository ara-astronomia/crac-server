import unittest
from gpiozero import Device
from crac_server.component.button_control import ButtonControl
from crac_protobuf.button_pb2 import ButtonStatus


class TestButtonControl(unittest.TestCase):

    PIN = 21

    def tearDown(self):
        Device.pin_factory.reset()

    def test_construction_does_not_drive_the_pin(self):
        """A restarted process must not turn a switch off on its own: the
        pin keeps whatever a previous run left it at."""
        pin = Device.pin_factory.pin(self.PIN)
        pin.function = "output"
        pin.state = True

        ButtonControl(self.PIN)

        self.assertTrue(pin.state)

    def test_on_turns_the_pin_on(self):
        button = ButtonControl(self.PIN)
        button.on()
        self.assertEqual(ButtonStatus.ON, button.get_status())

    def test_off_turns_the_pin_off(self):
        button = ButtonControl(self.PIN)
        button.on()
        button.off()
        self.assertEqual(ButtonStatus.OFF, button.get_status())
