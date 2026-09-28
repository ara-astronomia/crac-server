import time
import unittest
from gpiozero import Device
from crac_protobuf.curtains_pb2 import CurtainOrientation, CurtainStatus
from crac_server.component.curtains.curtains import Curtain
from crac_server.component.curtains.simulator.curtains import MockCurtain


class TestCurtainEnable(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = MockCurtain(
            rotary_encoder={"a": 5, "b": 6, "max_steps": 215},
            curtain_closed={"pin": 12, "pull_up": True},
            curtain_open={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )

    def tearDown(self):
        self.curtain.__stop__()
        Device.pin_factory.reset()

    def test_enable_cancels_pending_disable_intent(self):
        # enable() while disable() is still on its way down: left True,
        # to_disable would disable the motor at the next full close
        self.curtain.curtain_closed.pin.drive_high()
        self.curtain.disable()
        self.assertTrue(self.curtain.to_disable)

        self.curtain.enable()
        self.assertFalse(self.curtain.to_disable)

    def test_enable_turns_motor_enable_device_on(self):
        self.curtain.motor.enable_device.off()
        self.curtain.enable()
        self.assertTrue(self.curtain.motor.enable_device.value)


class TestCurtainDisable(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = Curtain(
            rotary_encoder={"a": 5, "b": 6, "max_steps": 215},
            curtain_closed={"pin": 12, "pull_up": True},
            curtain_open={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_WEST),
        )
        self.curtain.motor.enable_device.on()
        self.curtain.rotary_encoder.steps = 199

    def tearDown(self):
        self.curtain.__stop__()
        Device.pin_factory.reset()

    def test_a_curtain_at_rest_keeps_going_down_past_its_first_step(self):
        self.curtain.disable()
        self.curtain.rotary_encoder.steps = 198
        self.curtain.__check_and_stop__()

        self.assertEqual(-1, self.curtain.motor.value)

    def _simulated(self, steps):
        simulated = MockCurtain(
            rotary_encoder={"a": 7, "b": 8, "max_steps": 215},
            curtain_closed={"pin": 16, "pull_up": True},
            curtain_open={"pin": 21, "pull_up": True},
            motor={"forward": 23, "backward": 24, "enable": 25, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )
        self.addCleanup(simulated.__stop__)
        simulated.motor.enable_device.on()
        simulated.curtain_closed.pin.drive_high()
        simulated.rotary_encoder.steps = steps
        return simulated

    def _walk_down_to(self, steps):
        while self.curtain.motor.value and self.curtain.steps() > steps:
            self.curtain.rotary_encoder.steps = self.curtain.steps() - 1
            self.curtain.__check_and_stop__()

    def test_the_simulated_encoder_turns_with_the_motor_even_without_a_target(self):
        simulated = self._simulated(30)

        simulated.__close__()
        simulated.t.join(timeout=2)

        self.assertEqual(29, simulated.steps())
        self.assertEqual(0, simulated.motor.value)

    def test_a_curtain_at_rest_is_disabled_on_the_closed_limit_switch(self):
        self.curtain.disable()
        self.curtain.curtain_closed.pin.drive_low()

        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, self.curtain.get_status())

    def test_without_the_closed_switch_the_encoder_stops_the_run_at_sub_min(self):
        self.curtain.disable()
        self._walk_down_to(-40)

        self.assertEqual(-10, self.curtain.steps())
        self.assertEqual(0, self.curtain.motor.value)

    def test_a_curtain_stopped_at_sub_min_is_trusted_to_be_down(self):
        self.curtain.disable()
        self._walk_down_to(-40)

        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, self.curtain.get_status())

    def test_a_curtain_at_sub_min_does_not_start_again(self):
        self.curtain.rotary_encoder.steps = -10
        self.curtain.disable()

        self.assertEqual(0, self.curtain.motor.value)
        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, self.curtain.get_status())

    def test_a_simulated_curtain_disabled_while_opening_reaches_the_closed_switch(self):
        simulated = self._simulated(5)
        simulated.target = 150
        simulated.__open__()
        time.sleep(0.5)

        simulated.disable()
        deadline = time.monotonic() + 5
        while simulated.get_status() != CurtainStatus.CURTAIN_DISABLED and time.monotonic() < deadline:
            time.sleep(0.1)

        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, simulated.get_status())
