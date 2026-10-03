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

    def test_without_the_closed_switch_the_curtain_keeps_going_down(self):
        self.curtain.disable()
        self._walk_down_to(-40)

        self.assertEqual(-40, self.curtain.steps())
        self.assertEqual(-1, self.curtain.motor.value)
        self.assertEqual(CurtainStatus.CURTAIN_DISABLING, self.curtain.get_status())

    def test_the_closed_switch_stops_and_disables_the_curtain(self):
        self.curtain.disable()
        self._walk_down_to(-40)

        self._press_closed_switch()

        self.assertEqual(0, self.curtain.steps())
        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, self.curtain.get_status())

    def test_a_curtain_below_zero_without_the_closed_switch_starts_again(self):
        self.curtain.rotary_encoder.steps = -10
        self.curtain.disable()

        self.assertEqual(-1, self.curtain.motor.value)

    def _press_closed_switch(self):
        self.curtain.curtain_closed.pin.drive_low()
        deadline = time.monotonic() + 1
        while self.curtain.motor.value and time.monotonic() < deadline:
            time.sleep(0.01)

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


class TestCurtainCloseToTheSwitch(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = Curtain(
            rotary_encoder={"a": 5, "b": 6, "max_steps": 215},
            curtain_closed={"pin": 12, "pull_up": True},
            curtain_open={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )
        self.curtain.motor.enable_device.on()
        self.curtain.rotary_encoder.steps = 50

    def tearDown(self):
        self.curtain.__stop__()
        Device.pin_factory.reset()

    def _walk_down_to(self, steps):
        while self.curtain.motor.value and self.curtain.steps() > steps:
            self.curtain.rotary_encoder.steps = self.curtain.steps() - 1
            self.curtain.__check_and_stop__()

    def test_the_encoder_at_zero_does_not_stop_a_closing_curtain(self):
        self.curtain.move(0)
        self._walk_down_to(-5)

        self.assertEqual(-1, self.curtain.motor.value)

    def test_the_closed_switch_stops_a_closing_curtain_and_resets_the_steps(self):
        self.curtain.move(0)
        self._walk_down_to(-5)

        self.curtain.curtain_closed.pin.drive_low()
        deadline = time.monotonic() + 1
        while self.curtain.motor.value and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(0, self.curtain.motor.value)
        self.assertEqual(0, self.curtain.steps())
        self.assertEqual(CurtainStatus.CURTAIN_CLOSED, self.curtain.get_status())

    def test_a_curtain_at_zero_steps_but_off_the_switch_closes(self):
        self.curtain.rotary_encoder.steps = 0

        self.curtain.move(0)

        self.assertEqual(-1, self.curtain.motor.value)

    def test_a_curtain_on_the_closed_switch_does_not_move(self):
        self.curtain.rotary_encoder.steps = 0
        self.curtain.curtain_closed.pin.drive_low()

        self.curtain.move(0)

        self.assertEqual(0, self.curtain.motor.value)

    def test_a_curtain_below_zero_is_not_in_danger(self):
        self.curtain.rotary_encoder.steps = -30

        self.assertEqual(CurtainStatus.CURTAIN_STOPPED, self.curtain.get_status())

    def test_a_closing_curtain_well_below_zero_is_not_in_danger(self):
        self.curtain.move(0)
        self._walk_down_to(-10)

        self.assertEqual(CurtainStatus.CURTAIN_CLOSING, self.curtain.get_status())

    def test_a_partial_target_is_still_reached_by_the_encoder(self):
        self.curtain.move(20)
        self._walk_down_to(0)

        self.assertEqual(20, self.curtain.steps())
        self.assertEqual(0, self.curtain.motor.value)


class TestCurtainOpenToTheSwitch(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = Curtain(
            rotary_encoder={"a": 5, "b": 6, "max_steps": 0},
            curtain_closed={"pin": 12, "pull_up": True},
            curtain_open={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )
        self.curtain.motor.enable_device.on()
        self.curtain.rotary_encoder.steps = 150

    def tearDown(self):
        self.curtain.__stop__()
        Device.pin_factory.reset()

    def _walk_up_to(self, steps):
        while self.curtain.motor.value and self.curtain.steps() < steps:
            self.curtain.rotary_encoder.steps = self.curtain.steps() + 1
            self.curtain.__check_and_stop__()

    def test_the_encoder_at_full_travel_does_not_stop_an_opening_curtain(self):
        self.curtain.move(205)
        self._walk_up_to(260)

        self.assertEqual(260, self.curtain.steps())
        self.assertEqual(1, self.curtain.motor.value)
        self.assertEqual(CurtainStatus.CURTAIN_OPENING, self.curtain.get_status())

    def test_the_open_switch_stops_an_opening_curtain_and_sets_full_travel(self):
        self.curtain.move(205)
        self._walk_up_to(230)

        self.curtain.curtain_open.pin.drive_low()
        deadline = time.monotonic() + 1
        while self.curtain.motor.value and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(0, self.curtain.motor.value)
        self.assertEqual(205, self.curtain.steps())
        self.assertEqual(CurtainStatus.CURTAIN_OPENED, self.curtain.get_status())

    def test_a_curtain_at_full_travel_but_off_the_switch_opens(self):
        self.curtain.rotary_encoder.steps = 205

        self.curtain.move(205)

        self.assertEqual(1, self.curtain.motor.value)

    def test_a_curtain_on_the_open_switch_does_not_move(self):
        self.curtain.rotary_encoder.steps = 205
        self.curtain.curtain_open.pin.drive_low()

        self.curtain.move(205)

        self.assertEqual(0, self.curtain.motor.value)

    def test_a_curtain_above_full_travel_is_not_in_danger(self):
        self.curtain.rotary_encoder.steps = 230

        self.assertEqual(CurtainStatus.CURTAIN_STOPPED, self.curtain.get_status())


class TestCurtainFactoryEncoder(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()

    def tearDown(self):
        Device.pin_factory.reset()

    def test_the_encoder_of_a_built_curtain_has_no_step_limit(self):
        from crac_server.component.curtains.factory_curtain import FactoryCurtain

        curtain = FactoryCurtain.curtain(CurtainOrientation.CURTAIN_EAST, mock=False)

        self.assertEqual(0, curtain.rotary_encoder.max_steps)
