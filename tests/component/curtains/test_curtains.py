import time
import unittest
from unittest.mock import patch
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

    def test_a_curtain_left_disabled_halfway_gets_its_motor_back_to_go_down(self):
        self.curtain.motor.enable_device.off()
        self.assertEqual(CurtainStatus.CURTAIN_STOPPED, self.curtain.get_status())

        self.curtain.disable()

        self.assertTrue(self.curtain.motor.enable_device.value)
        self.assertEqual(-1, self.curtain.motor.value)

    def test_a_curtain_left_disabled_halfway_ends_up_disabled_on_the_closed_switch(self):
        self.curtain.motor.enable_device.off()
        self.curtain.disable()

        self._press_closed_switch()

        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, self.curtain.get_status())

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


def _curtain(orientation=CurtainOrientation.CURTAIN_EAST):
    return Curtain(
        rotary_encoder={"a": 5, "b": 6, "max_steps": 215},
        curtain_closed={"pin": 12, "pull_up": True},
        curtain_open={"pin": 13, "pull_up": True},
        motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
        orientation=CurtainOrientation.Name(orientation),
    )


class TestCurtainFullTravel(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = _curtain()
        self.curtain.motor.enable_device.on()

    def tearDown(self):
        self.curtain.__stop__()
        Device.pin_factory.reset()

    def test_a_curtain_stopped_at_full_travel_is_open(self):
        self.curtain.rotary_encoder.steps = 205

        self.assertEqual(CurtainStatus.CURTAIN_OPENED, self.curtain.get_status())

    def test_a_curtain_stopped_past_full_travel_is_open(self):
        self.curtain.rotary_encoder.steps = 210

        self.assertEqual(CurtainStatus.CURTAIN_OPENED, self.curtain.get_status())

    def test_a_curtain_stopped_short_of_full_travel_is_not_open(self):
        self.curtain.rotary_encoder.steps = 204

        self.assertEqual(CurtainStatus.CURTAIN_STOPPED, self.curtain.get_status())

    def test_a_curtain_on_the_open_switch_is_open_whatever_the_encoder_says(self):
        self.curtain.rotary_encoder.steps = 150
        self.curtain.curtain_open.pin.drive_low()
        self.curtain.rotary_encoder.steps = 150

        self.assertEqual(CurtainStatus.CURTAIN_OPENED, self.curtain.get_status())

    def test_full_travel_is_the_value_read_at_startup(self):
        with patch("crac_server.component.curtains.curtains.Config.getInt", return_value=100):
            self.assertEqual(205, self.curtain.full_travel)

    def test_a_simulated_curtain_never_reaches_the_open_switch(self):
        simulated = MockCurtain(
            rotary_encoder={"a": 7, "b": 8, "max_steps": 215},
            curtain_closed={"pin": 16, "pull_up": True},
            curtain_open={"pin": 21, "pull_up": True},
            motor={"forward": 23, "backward": 24, "enable": 25, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_WEST),
        )
        self.addCleanup(simulated.__stop__)
        simulated.motor.enable_device.on()
        simulated.curtain_closed.pin.drive_high()
        simulated.rotary_encoder.steps = 200
        simulated.target = 205
        simulated.__open__()
        simulated.t.join(timeout=3)

        self.assertEqual(205, simulated.steps())
        self.assertFalse(simulated.curtain_open.is_active)


class TestCurtainAtStartup(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()

    def tearDown(self):
        Device.pin_factory.reset()

    def test_a_curtain_off_the_closed_switch_starts_enabled_and_still(self):
        curtain = _curtain()

        self.assertTrue(curtain.motor.enable_device.value)
        self.assertEqual(0, curtain.motor.value)
        self.assertEqual(CurtainStatus.CURTAIN_STOPPED, curtain.get_status())

    def test_a_simulated_curtain_on_the_closed_switch_starts_disabled(self):
        simulated = MockCurtain(
            rotary_encoder={"a": 5, "b": 6, "max_steps": 215},
            curtain_closed={"pin": 12, "pull_up": True},
            curtain_open={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )

        self.assertFalse(simulated.motor.enable_device.value)
        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, simulated.get_status())


class TestCurtainReversal(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = _curtain()
        self.curtain.motor.enable_device.on()
        self.curtain.rotary_encoder.steps = 100

    def tearDown(self):
        self.curtain.__stop__()
        Device.pin_factory.reset()

    def _disable_recording_pauses(self):
        pauses = []
        with patch("crac_server.component.curtains.curtains.sleep",
                   side_effect=lambda seconds: pauses.append((seconds, self.curtain.motor.value))):
            self.curtain.disable()
        return pauses

    def test_an_opening_curtain_stops_and_pauses_before_going_down(self):
        self.curtain.move(150)

        pauses = self._disable_recording_pauses()

        self.assertEqual([(0.5, 0)], pauses)
        self.assertEqual(-1, self.curtain.motor.value)

    def test_a_curtain_at_rest_goes_down_without_pausing(self):
        pauses = self._disable_recording_pauses()

        self.assertEqual([], pauses)
        self.assertEqual(-1, self.curtain.motor.value)

    def _recording_pauses(self, start):
        pauses = []
        with patch("crac_server.component.curtains.curtains.sleep",
                   side_effect=lambda seconds: pauses.append((seconds, self.curtain.motor.value))):
            start()
        return pauses

    def test_closing_a_curtain_that_is_opening_stops_and_pauses_first(self):
        self.curtain.__open__()

        pauses = self._recording_pauses(self.curtain.__close__)

        self.assertEqual([(0.5, 0)], pauses)
        self.assertEqual(-1, self.curtain.motor.value)

    def test_opening_a_curtain_that_is_closing_stops_and_pauses_first(self):
        self.curtain.__close__()

        pauses = self._recording_pauses(self.curtain.__open__)

        self.assertEqual([(0.5, 0)], pauses)
        self.assertEqual(1, self.curtain.motor.value)

    def test_keeping_the_same_direction_does_not_pause(self):
        self.curtain.__open__()

        pauses = self._recording_pauses(self.curtain.__open__)

        self.assertEqual([], pauses)
        self.assertEqual(1, self.curtain.motor.value)
