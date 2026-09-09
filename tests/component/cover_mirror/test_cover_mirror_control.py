import logging
import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.cover_mirror_pb2 import CoverMirrorAction, CoverMirrorStatus
from crac_server.component.cover_mirror.cover_mirror_control import CoverMirrorControl
from crac_server.component.status_log import ErrorCause


class TestCoverMirrorControl(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        patcher = patch("crac_server.component.cover_mirror.cover_mirror_control.get_indigo_client")
        self.addCleanup(patcher.stop)
        mock_get_client = patcher.start()
        self.mock_client = MagicMock()
        mock_get_client.return_value = self.mock_client
        self.control = CoverMirrorControl(hostname="host", port=1)

    def test_init_connects_device(self):
        self.mock_client.connect_device.assert_called_once_with(self.control._name)

    async def test_open_sends_open_command(self):
        await self.control.open()
        sent = self.mock_client.send.call_args[0][0]
        self.assertEqual(sent["newSwitchVector"]["name"], "AUX_COVER")
        items = {i["name"]: i["value"] for i in sent["newSwitchVector"]["items"]}
        self.assertEqual(items, {"OPEN": True, "CLOSE": False})

    async def test_close_sends_close_command(self):
        await self.control.close()
        sent = self.mock_client.send.call_args[0][0]
        items = {i["name"]: i["value"] for i in sent["newSwitchVector"]["items"]}
        self.assertEqual(items, {"OPEN": False, "CLOSE": True})

    def test_get_status_reconnects_device_before_reading(self):
        self.mock_client.get_property.return_value = None
        self.control.get_status()
        self.assertEqual(self.mock_client.connect_device.call_count, 2)  # __init__ + get_status

    def test_get_status_open(self):
        self.mock_client.get_property.return_value = {
            "state": "Ok",
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_OPENED)

    def test_get_status_closed(self):
        self.mock_client.get_property.return_value = {
            "state": "Ok",
            "items": [{"name": "OPEN", "value": False}, {"name": "CLOSE", "value": True}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_CLOSED)

    def test_get_status_missing_property_is_error(self):
        self.mock_client.get_property.return_value = None
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_ERROR)

    def test_get_status_no_switch_true_is_error(self):
        self.mock_client.get_property.return_value = {
            "state": "Ok",
            "items": [{"name": "OPEN", "value": False}, {"name": "CLOSE", "value": False}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_ERROR)

    def test_get_status_alert_with_open_true_is_error(self):
        self.mock_client.get_property.return_value = {
            "state": "Alert",
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_ERROR)

    def test_get_status_alert_with_close_true_is_error(self):
        self.mock_client.get_property.return_value = {
            "state": "Alert",
            "items": [{"name": "OPEN", "value": False}, {"name": "CLOSE", "value": True}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_ERROR)

    def test_get_status_busy_with_open_true_is_opening(self):
        self.mock_client.get_property.return_value = {
            "state": "Busy",
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_OPENING)

    def test_get_status_busy_with_close_true_is_closing(self):
        self.mock_client.get_property.return_value = {
            "state": "Busy",
            "items": [{"name": "OPEN", "value": False}, {"name": "CLOSE", "value": True}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_CLOSING)

    def test_get_status_busy_with_no_switch_true_is_error(self):
        self.mock_client.get_property.return_value = {
            "state": "Busy",
            "items": [{"name": "OPEN", "value": False}, {"name": "CLOSE", "value": False}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_ERROR)

    def test_get_status_missing_state_is_error(self):
        self.mock_client.get_property.return_value = {
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        self.assertEqual(self.control.get_status(), CoverMirrorStatus.COVER_MIRROR_ERROR)

    def test_get_commanded_action_open(self):
        self.mock_client.get_property.return_value = {
            "state": "Alert",
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        self.assertEqual(self.control.get_commanded_action(), CoverMirrorAction.OPEN_COVER_MIRROR)

    def test_get_commanded_action_close(self):
        self.mock_client.get_property.return_value = {
            "state": "Alert",
            "items": [{"name": "OPEN", "value": False}, {"name": "CLOSE", "value": True}]
        }
        self.assertEqual(self.control.get_commanded_action(), CoverMirrorAction.CLOSE_COVER_MIRROR)

    def test_get_commanded_action_missing_property_is_default(self):
        self.mock_client.get_property.return_value = None
        self.assertEqual(self.control.get_commanded_action(), CoverMirrorAction.COVER_MIRROR_DEFAULT_ACTION)

    def test_get_commanded_action_no_switch_true_is_default(self):
        self.mock_client.get_property.return_value = {
            "state": "Alert",
            "items": [{"name": "OPEN", "value": False}, {"name": "CLOSE", "value": False}]
        }
        self.assertEqual(self.control.get_commanded_action(), CoverMirrorAction.COVER_MIRROR_DEFAULT_ACTION)

    def test_get_commanded_action_does_not_wait_for_a_missing_property(self):
        self.mock_client.get_property.return_value = None
        self.control.get_commanded_action()
        self.mock_client.get_property.assert_called_with(self.control._name, "AUX_COVER", timeout=0)

    LOGGER = "crac_server.component.cover_mirror.cover_mirror_control"

    def test_missing_property_is_logged_once(self):
        self.mock_client.get_property.return_value = None
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.control.get_status()
            self.control.get_status()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("[CoverMirror]", message)
        self.assertIn(ErrorCause.DEVICE_UNREACHABLE, message)

    def test_alert_state_is_logged_as_movement_not_confirmed(self):
        self.mock_client.get_property.return_value = {
            "state": "Alert",
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.control.get_status()
        message = captured.records[0].getMessage()
        self.assertIn(ErrorCause.MOVEMENT_NOT_CONFIRMED, message)
        self.assertIn("Alert", message)

    def test_recovery_after_an_alert_is_logged_at_info(self):
        self.mock_client.get_property.return_value = {
            "state": "Alert",
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        self.control.get_status()
        self.mock_client.get_property.return_value = {
            "state": "Ok",
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            self.control.get_status()
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)

    def test_a_healthy_reading_logs_nothing(self):
        self.mock_client.get_property.return_value = {
            "state": "Ok",
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        with self.assertNoLogs(self.LOGGER, level="INFO"):
            self.control.get_status()

    def test_missing_state_is_logged_as_state_not_recognized(self):
        self.mock_client.get_property.return_value = {
            "items": [{"name": "OPEN", "value": True}, {"name": "CLOSE", "value": False}]
        }
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.control.get_status()
        self.assertIn(ErrorCause.STATE_NOT_RECOGNIZED, captured.records[0].getMessage())
