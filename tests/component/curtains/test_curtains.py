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
        # regressione: disable() imposta to_disable=True, resettato solo dal
        # callback del finecorsa chiuso quando la tenda arriva fisicamente
        # chiusa (__reset_steps__/disable_motor). Se enable() viene chiamato
        # PRIMA che questo accada (tenda ancora in chiusura), to_disable
        # restava bloccato a True: la tenda si sarebbe ridisabilitata da
        # sola alla successiva chiusura completa, anche non voluta.
        self.curtain.curtain_closed.pin.drive_high()  # finecorsa chiuso non ancora attivo
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

    def test_the_simulated_encoder_turns_with_the_motor_even_without_a_target(self):
        simulated = MockCurtain(
            rotary_encoder={"a": 7, "b": 8, "max_steps": 215},
            curtain_closed={"pin": 16, "pull_up": True},
            curtain_open={"pin": 21, "pull_up": True},
            motor={"forward": 23, "backward": 24, "enable": 25, "pwm": False},
            orientation=CurtainOrientation.Name(CurtainOrientation.CURTAIN_EAST),
        )
        self.addCleanup(simulated.__stop__)
        simulated.motor.enable_device.on()
        simulated.rotary_encoder.steps = 30

        simulated.__close__()
        simulated.t.join(timeout=2)

        self.assertEqual(29, simulated.steps())
        self.assertEqual(0, simulated.motor.value)

    def test_a_curtain_at_rest_is_disabled_on_the_closed_limit_switch(self):
        self.curtain.disable()
        self.curtain.curtain_closed.pin.drive_low()

        self.assertEqual(CurtainStatus.CURTAIN_DISABLED, self.curtain.get_status())
