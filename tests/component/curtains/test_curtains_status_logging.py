import logging
import time
import unittest

from gpiozero import Device

from crac_protobuf.curtains_pb2 import CurtainOrientation
from crac_server.component.curtains.curtains import Curtain
from crac_server.component.curtains.simulator.curtains import MockCurtain
from crac_server.status_log import ErrorCause


def _curtain(orientation=CurtainOrientation.CURTAIN_EAST):
    return Curtain(
        encoder={"a": 5, "b": 6, "max_steps": 215},
        closed_switch={"pin": 12, "pull_up": True},
        open_switch={"pin": 13, "pull_up": True},
        motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
        orientation=CurtainOrientation.Name(orientation),
    )


class TestCurtainStatusLogging(unittest.TestCase):

    LOGGER = "crac_server.component.curtains.curtains"

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = MockCurtain(
            encoder={"a": 5, "b": 6, "max_steps": 215},
            closed_switch={"pin": 12, "pull_up": True},
            open_switch={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )

    def tearDown(self):
        self.curtain._stop()
        Device.pin_factory.reset()

    def _no_state_recognized(self):
        """Both switches active at once: no position matches."""
        self.curtain._open_switch.pin.drive_low()

    def test_unrecognized_state_is_logged_once_with_the_curtain_orientation(self):
        self._no_state_recognized()
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.curtain.get_status()
            self.curtain.get_status()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("CURTAIN_EAST", message)
        self.assertIn(ErrorCause.STATE_NOT_RECOGNIZED, message)
        self.assertIn("steps=", message)

    def test_recovery_is_logged_at_info(self):
        self._no_state_recognized()
        self.curtain.get_status()
        self.curtain._open_switch.pin.drive_high()
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            self.curtain.get_status()
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)

    def test_a_recognized_state_logs_no_error(self):
        with self.assertNoLogs(self.LOGGER, level="ERROR"):
            self.curtain.get_status()


class TestCurtainDangerLogging(unittest.TestCase):
    """The encoder counts beyond its safety stop: on site this is a wiring
    or encoder fault, so the test widens max_steps to reach the branch."""

    LOGGER = "crac_server.component.curtains.curtains"

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = Curtain(
            encoder={"a": 5, "b": 6, "max_steps": 300},
            closed_switch={"pin": 12, "pull_up": True},
            open_switch={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )

    def tearDown(self):
        self.curtain._stop()
        Device.pin_factory.reset()

    def _beyond_the_safety_step(self):
        self.curtain._closed_switch.pin.drive_high()
        self.curtain._encoder.steps = self.curtain._safety_step + 1

    def test_danger_is_logged_once_with_the_steps_read(self):
        self._beyond_the_safety_step()
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.curtain.get_status()
            self.curtain.get_status()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("CURTAIN_EAST", message)
        self.assertIn(ErrorCause.SAFETY_STEP_EXCEEDED, message)
        self.assertIn(f"steps={self.curtain._safety_step + 1}", message)

    def test_danger_recovery_is_logged_at_info(self):
        self._beyond_the_safety_step()
        self.curtain.get_status()
        self.curtain._closed_switch.pin.drive_low()
        self.curtain._encoder.steps = 0
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            self.curtain.get_status()
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)


class TestCurtainMovementLogging(unittest.TestCase):

    LOGGER = "crac_server.component.curtains.curtains"

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = _curtain()
        self.curtain._motor.enable_device.on()
        self.curtain._encoder.steps = 50

    def tearDown(self):
        self.curtain._stop()
        Device.pin_factory.reset()

    def _walk_down_one_step_at_a_time(self):
        while self.curtain._motor.value:
            self.curtain._encoder.steps = self.curtain.steps() - 1
            self.curtain._on_rotation()

    def test_a_move_logs_start_and_stop_with_orientation_and_steps(self):
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            self.curtain.move(20)
            self._walk_down_one_step_at_a_time()
        self.assertEqual(len(captured.records), 2)
        start, stop = (record.getMessage() for record in captured.records)
        self.assertIn("CURTAIN_EAST", start)
        self.assertIn("moving down towards step 20", start)
        self.assertIn("from step 50", start)
        self.assertIn("CURTAIN_EAST", stop)
        self.assertIn("stopped at step 20", stop)

    def test_a_move_on_a_disabled_motor_logs_nothing(self):
        self.curtain._motor.enable_device.off()
        with self.assertNoLogs(self.LOGGER, level="INFO"):
            self.curtain.move(150)

    def test_disable_logs_the_run_to_the_switch_and_the_motor_off(self):
        self.curtain._closed_switch.pin.drive_high()
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            self.curtain.disable()
            self.curtain._closed_switch.pin.drive_low()
            deadline = time.monotonic() + 1
            while self.curtain._motor.value and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(len(captured.records), 3)
        messages = [record.getMessage() for record in captured.records]
        self.assertIn("moving down towards step 0", messages[0])
        self.assertIn("stopped at step 0", messages[1])
        self.assertIn("motor disabled", messages[2])

    def test_a_repeated_disable_of_a_disabled_curtain_logs_nothing(self):
        self.curtain._closed_switch.pin.drive_high()
        self.curtain.disable()
        self.curtain._closed_switch.pin.drive_low()
        deadline = time.monotonic() + 1
        while self.curtain._motor.value and time.monotonic() < deadline:
            time.sleep(0.01)
        with self.assertNoLogs(self.LOGGER, level="INFO"):
            self.curtain.disable()

    def test_enable_logs_the_motor_on(self):
        self.curtain._motor.enable_device.off()
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            self.curtain.enable()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("CURTAIN_EAST", message)
        self.assertIn("motor enabled", message)
