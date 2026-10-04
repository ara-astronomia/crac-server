import time
import unittest
from unittest.mock import patch
from gpiozero import Device
from crac_protobuf.curtains_pb2 import CurtainOrientation, CurtainStatus
from crac_server.component.curtains.curtains import Curtain
from crac_server.component.curtains.simulator.curtains import MockCurtain
from crac_server.component.curtains.factory_curtain import build_curtain


class TestCurtainEnable(unittest.TestCase):

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

    def test_enable_cancels_pending_disable_intent(self):
        """enable() while disable() is still on its way down: left True,
        to_disable would disable the motor at the next full close."""
        self.curtain._closed_switch.pin.drive_high()
        self.curtain.disable()
        self.assertTrue(self.curtain._to_disable)

        self.curtain.enable()
        self.assertFalse(self.curtain._to_disable)

    def test_enable_turns_motor_enable_device_on(self):
        self.curtain._motor.enable_device.off()
        self.curtain.enable()
        self.assertTrue(self.curtain._motor.enable_device.value)


class TestCurtainDisable(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = Curtain(
            encoder={"a": 5, "b": 6, "max_steps": 215},
            closed_switch={"pin": 12, "pull_up": True},
            open_switch={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_WEST),
        )
        self.curtain._motor.enable_device.on()
        self.curtain._encoder.steps = 199

    def tearDown(self):
        self.curtain._stop()
        Device.pin_factory.reset()

    def test_a_curtain_at_rest_keeps_going_down_past_its_first_step(self):
        self.curtain.disable()
        self.curtain._encoder.steps = 198
        self.curtain._on_rotation()

        self.assertEqual(-1, self.curtain._motor.value)

    def _simulated(self, steps):
        simulated = MockCurtain(
            encoder={"a": 7, "b": 8, "max_steps": 215},
            closed_switch={"pin": 16, "pull_up": True},
            open_switch={"pin": 21, "pull_up": True},
            motor={"forward": 23, "backward": 24, "enable": 25, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )
        self.addCleanup(simulated._stop)
        simulated._motor.enable_device.on()
        simulated._closed_switch.pin.drive_high()
        simulated._encoder.steps = steps
        return simulated

    def _walk_down_to(self, steps):
        while self.curtain._motor.value and self.curtain.steps() > steps:
            self.curtain._encoder.steps = self.curtain.steps() - 1
            self.curtain._on_rotation()

    def test_the_simulated_encoder_turns_with_the_motor_even_without_a_target(self):
        simulated = self._simulated(30)

        simulated._close()
        simulated._thread.join(timeout=2)

        self.assertEqual(29, simulated.steps())
        self.assertEqual(0, simulated._motor.value)

    def test_without_the_closed_switch_the_curtain_keeps_going_down(self):
        self.curtain.disable()
        self._walk_down_to(-40)

        self.assertEqual(-40, self.curtain.steps())
        self.assertEqual(-1, self.curtain._motor.value)
        self.assertEqual(CurtainStatus.CURTAIN_DISABLING, self.curtain.get_status())

    def test_the_closed_switch_stops_and_disables_the_curtain(self):
        self.curtain.disable()
        self._walk_down_to(-40)

        self._press_closed_switch()

        self.assertEqual(0, self.curtain.steps())
        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, self.curtain.get_status())

    def test_a_curtain_below_zero_without_the_closed_switch_starts_again(self):
        self.curtain._encoder.steps = -10
        self.curtain.disable()

        self.assertEqual(-1, self.curtain._motor.value)

    def test_an_operator_disable_gets_the_motor_of_a_curtain_left_halfway_back(self):
        self.curtain._motor.enable_device.off()
        self.assertEqual(CurtainStatus.CURTAIN_STOPPED, self.curtain.get_status())

        self.curtain.disable(power_motor=True)

        self.assertTrue(self.curtain._motor.enable_device.value)
        self.assertEqual(-1, self.curtain._motor.value)

    def test_an_automatic_disable_never_powers_a_disabled_motor(self):
        """A curtain down on a broken closed switch looks halfway too: powering
        its motor on every poll would push it against the bottom, unattended."""
        self.curtain._motor.enable_device.off()

        self.curtain.disable()

        self.assertFalse(self.curtain._motor.enable_device.value)

    def test_a_curtain_left_disabled_halfway_ends_up_disabled_on_the_closed_switch(self):
        self.curtain._motor.enable_device.off()
        self.curtain.disable(power_motor=True)

        self._press_closed_switch()

        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, self.curtain.get_status())

    def _press_closed_switch(self):
        self.curtain._closed_switch.pin.drive_low()
        deadline = time.monotonic() + 1
        while self.curtain._motor.value and time.monotonic() < deadline:
            time.sleep(0.01)

    def test_a_simulated_curtain_disabled_while_opening_reaches_the_closed_switch(self):
        simulated = self._simulated(5)
        simulated._target = 150
        simulated._open()
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
            encoder={"a": 5, "b": 6, "max_steps": 215},
            closed_switch={"pin": 12, "pull_up": True},
            open_switch={"pin": 13, "pull_up": True},
            motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )
        self.curtain._motor.enable_device.on()
        self.curtain._encoder.steps = 50

    def tearDown(self):
        self.curtain._stop()
        Device.pin_factory.reset()

    def _walk_down_to(self, steps):
        while self.curtain._motor.value and self.curtain.steps() > steps:
            self.curtain._encoder.steps = self.curtain.steps() - 1
            self.curtain._on_rotation()

    def test_the_encoder_at_zero_does_not_stop_a_closing_curtain(self):
        self.curtain.move(0)
        self._walk_down_to(-5)

        self.assertEqual(-1, self.curtain._motor.value)

    def test_the_closed_switch_stops_a_closing_curtain_and_resets_the_steps(self):
        self.curtain.move(0)
        self._walk_down_to(-5)

        self.curtain._closed_switch.pin.drive_low()
        deadline = time.monotonic() + 1
        while self.curtain._motor.value and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(0, self.curtain._motor.value)
        self.assertEqual(0, self.curtain.steps())
        self.assertEqual(CurtainStatus.CURTAIN_CLOSED, self.curtain.get_status())

    def test_a_curtain_at_zero_steps_but_off_the_switch_closes(self):
        self.curtain._encoder.steps = 0

        self.curtain.move(0)

        self.assertEqual(-1, self.curtain._motor.value)

    def test_a_curtain_on_the_closed_switch_does_not_move(self):
        self.curtain._encoder.steps = 0
        self.curtain._closed_switch.pin.drive_low()

        self.curtain.move(0)

        self.assertEqual(0, self.curtain._motor.value)

    def test_a_curtain_below_zero_is_not_in_danger(self):
        self.curtain._encoder.steps = -30

        self.assertEqual(CurtainStatus.CURTAIN_STOPPED, self.curtain.get_status())

    def test_a_closing_curtain_well_below_zero_is_not_in_danger(self):
        self.curtain.move(0)
        self._walk_down_to(-10)

        self.assertEqual(CurtainStatus.CURTAIN_CLOSING, self.curtain.get_status())

    def test_a_partial_target_is_still_reached_by_the_encoder(self):
        self.curtain.move(20)
        self._walk_down_to(0)

        self.assertEqual(20, self.curtain.steps())
        self.assertEqual(0, self.curtain._motor.value)


def _curtain(orientation=CurtainOrientation.CURTAIN_EAST):
    return Curtain(
        encoder={"a": 5, "b": 6, "max_steps": 215},
        closed_switch={"pin": 12, "pull_up": True},
        open_switch={"pin": 13, "pull_up": True},
        motor={"forward": 19, "backward": 26, "enable": 20, "pwm": False},
        orientation=CurtainOrientation.Name(orientation),
    )


class TestCurtainFullTravel(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = _curtain()
        self.curtain._motor.enable_device.on()

    def tearDown(self):
        self.curtain._stop()
        Device.pin_factory.reset()

    def test_a_curtain_stopped_at_full_travel_is_open(self):
        self.curtain._encoder.steps = 205

        self.assertEqual(CurtainStatus.CURTAIN_OPENED, self.curtain.get_status())

    def test_a_curtain_stopped_past_full_travel_is_open(self):
        self.curtain._encoder.steps = 210

        self.assertEqual(CurtainStatus.CURTAIN_OPENED, self.curtain.get_status())

    def test_a_curtain_stopped_short_of_full_travel_is_not_open(self):
        self.curtain._encoder.steps = 204

        self.assertEqual(CurtainStatus.CURTAIN_STOPPED, self.curtain.get_status())

    def test_a_curtain_on_the_open_switch_is_open_whatever_the_encoder_says(self):
        self.curtain._encoder.steps = 150
        self.curtain._open_switch.pin.drive_low()
        self.curtain._encoder.steps = 150

        self.assertEqual(CurtainStatus.CURTAIN_OPENED, self.curtain.get_status())

    def test_full_travel_is_the_value_read_at_startup(self):
        with patch("crac_server.component.curtains.curtains.Config.getInt", return_value=100):
            self.assertEqual(205, self.curtain.full_travel)

    def test_a_simulated_curtain_never_reaches_the_open_switch(self):
        simulated = MockCurtain(
            encoder={"a": 7, "b": 8, "max_steps": 215},
            closed_switch={"pin": 16, "pull_up": True},
            open_switch={"pin": 21, "pull_up": True},
            motor={"forward": 23, "backward": 24, "enable": 25, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_WEST),
        )
        self.addCleanup(simulated._stop)
        simulated._motor.enable_device.on()
        simulated._closed_switch.pin.drive_high()
        simulated._encoder.steps = 200
        simulated._target = 205
        simulated._open()
        simulated._thread.join(timeout=3)

        self.assertEqual(205, simulated.steps())
        self.assertFalse(simulated._open_switch.is_active)


class TestCurtainAtStartup(unittest.TestCase):
    """Whatever position a curtain starts in, it goes down and is disabled."""

    def setUp(self):
        Device.pin_factory.reset()

    def tearDown(self):
        Device.pin_factory.reset()

    def test_a_curtain_off_the_closed_switch_goes_down_to_be_disabled(self):
        curtain = build_curtain(CurtainOrientation.CURTAIN_EAST)
        self.addCleanup(curtain._stop)

        self.assertTrue(curtain._motor.enable_device.value)
        self.assertEqual(-1, curtain._motor.value)
        self.assertEqual(CurtainStatus.CURTAIN_DISABLING, curtain.get_status())

    def test_a_simulated_curtain_starts_disabled_on_its_closed_switch(self):
        simulated = build_curtain(CurtainOrientation.CURTAIN_EAST, mock=True)

        self.assertFalse(simulated._motor.enable_device.value)
        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, simulated.get_status())


class TestCurtainReversal(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.curtain = _curtain()
        self.curtain._motor.enable_device.on()
        self.curtain._encoder.steps = 100

    def tearDown(self):
        self.curtain._stop()
        Device.pin_factory.reset()

    def _disable_recording_pauses(self):
        pauses = []
        with patch("crac_server.component.curtains.curtains.sleep",
                   side_effect=lambda seconds: pauses.append((seconds, self.curtain._motor.value))):
            self.curtain.disable()
        return pauses

    def test_an_opening_curtain_stops_and_pauses_before_going_down(self):
        self.curtain.move(150)

        pauses = self._disable_recording_pauses()

        self.assertEqual([(0.5, 0)], pauses)
        self.assertEqual(-1, self.curtain._motor.value)

    def test_a_curtain_at_rest_goes_down_without_pausing(self):
        pauses = self._disable_recording_pauses()

        self.assertEqual([], pauses)
        self.assertEqual(-1, self.curtain._motor.value)

    def _recording_pauses(self, start):
        pauses = []
        with patch("crac_server.component.curtains.curtains.sleep",
                   side_effect=lambda seconds: pauses.append((seconds, self.curtain._motor.value))):
            start()
        return pauses

    def test_closing_a_curtain_that_is_opening_stops_and_pauses_first(self):
        self.curtain._open()

        pauses = self._recording_pauses(self.curtain._close)

        self.assertEqual([(0.5, 0)], pauses)
        self.assertEqual(-1, self.curtain._motor.value)

    def test_opening_a_curtain_that_is_closing_stops_and_pauses_first(self):
        self.curtain._close()

        pauses = self._recording_pauses(self.curtain._open)

        self.assertEqual([(0.5, 0)], pauses)
        self.assertEqual(1, self.curtain._motor.value)

    def test_keeping_the_same_direction_does_not_pause(self):
        self.curtain._open()

        pauses = self._recording_pauses(self.curtain._open)

        self.assertEqual([], pauses)
        self.assertEqual(1, self.curtain._motor.value)
