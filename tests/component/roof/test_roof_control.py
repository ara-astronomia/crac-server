# test open roof
import unittest
from unittest.mock import patch
from gpiozero import Device
from crac_server.component.roof.roof_control import RoofControl
from crac_protobuf.roof_pb2 import RoofStatus
from crac_server.component.roof.simulator.roof_control import MockRoofControl


class TestRoofControl(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        # Importare questo modulo attiva crac_server.component.roof.__init__,
        # che crea il singleton ROOF riservando già il pin GPIO del tetto
        # (switch_roof) prima ancora che parta il primo test: va rilasciato
        # qui, altrimenti pure il primissimo test fallisce con GPIOPinInUse.
        Device.pin_factory.reset()

    def tearDown(self):
        # Ogni test riserva lo stesso pin su una nuova istanza di
        # RoofControl/MockRoofControl - va rilasciato anche tra un test e
        # l'altro, non solo prima del primo.
        Device.pin_factory.reset()

    def test_status_is_opening(self):
        roof_control = MockRoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        roof_control.motor.value = True
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_OPENING)

    def test_status_is_closing(self):
        roof_control = MockRoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        roof_control.motor.value = False
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_CLOSING)

    def test_status_is_closed(self):
        roof_control = MockRoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_low()
        roof_control.motor.value = False
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_CLOSED)

    def test_status_is_opened(self):
        roof_control = MockRoofControl()
        roof_control.roof_open_switch.pin.drive_low()
        roof_control.roof_closed_switch.pin.drive_high()
        roof_control.motor.value = True
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_OPENED)

    def test_status_is_error(self):
        roof_control = MockRoofControl()
        roof_control.roof_open_switch.pin.drive_low()
        roof_control.roof_closed_switch.pin.drive_low()
        roof_control.motor.value = True
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_ERROR)
    
    async def test_open_roof(self):
        roof_control = MockRoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        await roof_control.open()
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_OPENED)
    
    async def test_close_roof(self):
        roof_control = MockRoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        await roof_control.close()
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_CLOSED)

    async def test_when_roof_is_blocked_while_opening_then_it_will_close(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        with patch.object(roof_control.roof_open_switch, 'wait_for_active', return_value=False) as mockedroofopen:
            with patch.object(roof_control.roof_closed_switch, 'wait_for_active', return_value=True) as mockedroofclosed:
                is_open = await roof_control.open()
                mockedroofopen.assert_called_once()
                mockedroofclosed.assert_called_once()
                self.assertEqual(is_open, True)
