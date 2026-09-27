import unittest
from unittest.mock import patch

from gpiozero import Device

from crac_protobuf.roof_pb2 import RoofAction, RoofRequest
from crac_server.component.roof.roof_control import RoofControl
from crac_server.converter.roof_converter import RoofConverter, RoofMediator


class TestRoofButtonInError(unittest.TestCase):
    """
    In error the button offers the command against the way the motor pin is
    set: the other one is already on the pin and would change nothing.
    """

    def setUp(self):
        Device.pin_factory.reset()

    def tearDown(self):
        Device.pin_factory.reset()

    def _button(self, motor_on):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_low()
        roof_control.roof_closed_switch.pin.drive_low()
        roof_control.motor.value = motor_on
        with patch("crac_server.converter.roof_converter.roof", return_value=roof_control):
            mediator = RoofMediator(RoofRequest(action=RoofAction.CHECK_ROOF))
        return RoofConverter().convert(mediator).button_gui

    def test_with_the_motor_closing_it_offers_to_open(self):
        self.assertEqual(RoofAction.OPEN, self._button(motor_on=False).metadata)

    def test_with_the_motor_opening_it_offers_to_close(self):
        self.assertEqual(RoofAction.CLOSE, self._button(motor_on=True).metadata)


if __name__ == "__main__":
    unittest.main()
