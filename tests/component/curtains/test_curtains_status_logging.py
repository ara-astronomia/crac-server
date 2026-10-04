import logging
import unittest
from unittest.mock import patch

from gpiozero import Device

from crac_protobuf.curtains_pb2 import CurtainOrientation
from crac_server.component.curtains.simulator.curtains import MockCurtain
from crac_server.status_log import ErrorCause


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
        predicates = ["_is_danger", "_is_disabled", "_is_open", "_is_closed", "_is_stopped"]
        patchers = [patch.object(self.curtain, name, return_value=False) for name in predicates]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unrecognized_state_is_logged_once_with_the_curtain_orientation(self):
        self._no_state_recognized()
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.curtain.get_status()
            self.curtain.get_status()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("CURTAIN_EAST", message)
        self.assertIn(ErrorCause.STATE_NOT_RECOGNIZED, message)

    def test_recovery_is_logged_at_info(self):
        self._no_state_recognized()
        self.curtain.get_status()
        with patch.object(self.curtain, "_is_closed", return_value=True):
            with self.assertLogs(self.LOGGER, level="INFO") as captured:
                self.curtain.get_status()
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)

    def test_a_recognized_state_logs_no_error(self):
        with self.assertNoLogs(self.LOGGER, level="ERROR"):
            self.curtain.get_status()
