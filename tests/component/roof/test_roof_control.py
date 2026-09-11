# test open roof
import asyncio
import logging
from time import sleep
import unittest
from unittest.mock import patch
from gpiozero import Device
from crac_server.component.roof.roof_control import RoofControl
from crac_protobuf.roof_pb2 import RoofStatus
from crac_server.component.roof.simulator.roof_pins import simulated_roof
from crac_server.config import Config
from crac_server.status_log import ErrorCause


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
        # RoofControl - va rilasciato anche tra un test e l'altro, non solo
        # prima del primo.
        Device.pin_factory.reset()

    def test_status_is_opening(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        roof_control.motor.value = True
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_OPENING)

    def test_status_is_closing(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        roof_control.motor.value = False
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_CLOSING)

    def test_status_is_closed(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_low()
        roof_control.motor.value = False
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_CLOSED)

    def test_status_is_opened(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_low()
        roof_control.roof_closed_switch.pin.drive_high()
        roof_control.motor.value = True
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_OPENED)

    def test_status_is_error(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_low()
        roof_control.roof_closed_switch.pin.drive_low()
        roof_control.motor.value = True
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_ERROR)
    
    async def test_open_roof(self):
        roof_control = simulated_roof(travel_seconds=0.2)
        self.assertTrue(await roof_control.open())
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_OPENED)

    async def test_close_roof(self):
        roof_control = simulated_roof(travel_seconds=0.2)
        await roof_control.open()
        self.assertTrue(await roof_control.close())
        self.assertEqual(roof_control.get_status(), RoofStatus.ROOF_CLOSED)

    async def test_the_roof_tells_it_is_running_while_it_travels(self):
        """The simulated travel is what makes the intermediate states visible
        on the test stack: the roof is neither open nor closed for a while,
        and the server keeps answering throughout."""
        roof_control = simulated_roof(travel_seconds=0.3)

        run = asyncio.create_task(roof_control.open())
        await asyncio.sleep(0.1)
        self.assertEqual(RoofStatus.ROOF_OPENING, roof_control.get_status())

        await run
        self.assertEqual(RoofStatus.ROOF_OPENED, roof_control.get_status())

    async def test_the_run_does_not_stop_the_server_from_answering(self):
        """The roof takes seconds to reach the end of its run: for that whole
        time the event loop must stay free, or no other RPC gets an answer."""
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        order = []

        async def roof_run():
            with patch.object(
                roof_control.roof_open_switch, "wait_for_active",
                side_effect=self.__limit_switch_trips_late,
            ):
                await roof_control.open()
            order.append("roof")

        async def other_rpc():
            await asyncio.sleep(0.05)
            order.append("other rpc")

        await asyncio.gather(roof_run(), other_rpc())
        self.assertEqual(["other rpc", "roof"], order)

    def __limit_switch_trips_late(self, timeout):
        sleep(0.3)
        return True

    def test_a_motor_pin_already_taken_is_not_left_silently_unwired(self):
        """A pin already in the factory comes back as it is, keeping its own
        class: the roof would then wait out its timeout on every run, with
        nothing saying the simulation did not install."""
        Device.pin_factory.pin(Config.getInt("switch_roof", "roof_board"))

        with self.assertRaises(RuntimeError):
            simulated_roof()

    async def test_when_roof_is_blocked_while_opening_then_it_will_close(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_high()
        with patch.object(roof_control.roof_open_switch, 'wait_for_active', return_value=False) as mockedroofopen:
            with patch.object(roof_control.roof_closed_switch, 'wait_for_active', return_value=True) as mockedroofclosed:
                is_open = await roof_control.open()
                mockedroofopen.assert_called_once()
                mockedroofclosed.assert_called_once()
                self.assertFalse(is_open)


class TestRoofControlStatusLogging(unittest.TestCase):

    LOGGER = "crac_server.component.roof.roof_control"

    @classmethod
    def setUpClass(cls):
        Device.pin_factory.reset()

    def tearDown(self):
        Device.pin_factory.reset()

    def _roof_with_inconsistent_sensors(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_low()
        roof_control.roof_closed_switch.pin.drive_low()
        return roof_control

    def test_inconsistent_sensors_are_logged_once(self):
        roof_control = self._roof_with_inconsistent_sensors()
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            roof_control.get_status()
            roof_control.get_status()
            roof_control.get_status()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("[Roof]", message)
        self.assertIn(ErrorCause.SENSORS_INCONSISTENT, message)

    def test_safety_block_is_told_apart_from_a_broken_sensor(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_low()
        roof_control.motor.value = False
        roof_control.is_blocked = True
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            roof_control.get_status()
        self.assertIn(ErrorCause.BLOCKED_BY_SAFETY, captured.records[0].getMessage())

    def test_recovery_is_logged_at_info(self):
        roof_control = self._roof_with_inconsistent_sensors()
        roof_control.get_status()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.motor.value = False
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            roof_control.get_status()
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)

    def test_a_healthy_roof_logs_no_error(self):
        roof_control = RoofControl()
        roof_control.roof_open_switch.pin.drive_high()
        roof_control.roof_closed_switch.pin.drive_low()
        roof_control.motor.value = False
        with self.assertNoLogs(self.LOGGER, level="ERROR"):
            roof_control.get_status()
