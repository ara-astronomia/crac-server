import logging
import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.telescope_pb2 import TelescopeSpeed, TelescopeStatus
from crac_server.status_log import ErrorCause
from crac_server.component.telescope.indigo.telescope import Telescope


class TestTelescopeStatusLogging(unittest.TestCase):

    LOGGER = "crac_server.component.telescope.telescope"

    def setUp(self):
        patcher = patch("crac_server.component.telescope.indigo.telescope.get_indigo_client")
        self.addCleanup(patcher.stop)
        mock_get_client = patcher.start()
        mock_get_client.return_value = MagicMock()
        self.telescope = Telescope(hostname="host", port=1)

    def test_lost_is_logged_once_as_unreachable(self):
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.telescope.status = TelescopeStatus.LOST
            self.telescope.status = TelescopeStatus.LOST
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("[Telescope]", message)
        self.assertIn(ErrorCause.DEVICE_UNREACHABLE, message)

    def test_error_is_logged_as_unexpected_failure(self):
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.telescope.status = TelescopeStatus.ERROR
        self.assertIn(ErrorCause.UNEXPECTED_FAILURE, captured.records[0].getMessage())

    def test_recovery_is_logged_at_info(self):
        self.telescope.status = TelescopeStatus.LOST
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            self.telescope.status = TelescopeStatus.PARKED
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)

    def test_status_is_still_readable_after_being_set(self):
        self.telescope.status = TelescopeStatus.PARKED
        self.assertEqual(self.telescope.status, TelescopeStatus.PARKED)

    def test_healthy_transitions_log_nothing(self):
        with self.assertNoLogs(self.LOGGER, level="INFO"):
            self.telescope.status = TelescopeStatus.PARKED
            self.telescope.status = TelescopeStatus.EAST


class TestTelescopeSpeedLogging(unittest.TestCase):

    LOGGER = "crac_server.component.telescope.indigo.telescope"

    def setUp(self):
        patcher = patch("crac_server.component.telescope.indigo.telescope.get_indigo_client")
        self.addCleanup(patcher.stop)
        mock_get_client = patcher.start()
        self.mock_client = MagicMock()
        mock_get_client.return_value = self.mock_client
        self.telescope = Telescope(hostname="host", port=1)

    def _stub_properties(self, props: dict):
        def get_property(device, name, timeout=2.0):
            return props.get(name)
        self.mock_client.get_property.side_effect = get_property

    def _tracking_on(self):
        return {"items": [{"name": "ON", "value": True}]}

    def test_coordinates_in_alert_are_logged_once(self):
        self._stub_properties({
            "MOUNT_TRACKING": self._tracking_on(),
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Alert"},
        })
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.telescope._Telescope__retrieve_speed()
            self.telescope._Telescope__retrieve_speed()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("[Telescope speed]", message)
        self.assertIn(ErrorCause.STATE_NOT_RECOGNIZED, message)
        self.assertIn("Alert", message)

    def test_unreadable_properties_are_logged_as_unreachable(self):
        self._stub_properties({})
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.telescope._Telescope__retrieve_speed()
        self.assertIn(ErrorCause.DEVICE_UNREACHABLE, captured.records[0].getMessage())

    def test_recovery_is_logged_at_info(self):
        self._stub_properties({})
        self.telescope._Telescope__retrieve_speed()
        self._stub_properties({
            "MOUNT_TRACKING": self._tracking_on(),
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Ok"},
        })
        with self.assertLogs(self.LOGGER, level="INFO") as captured:
            self.telescope._Telescope__retrieve_speed()
        self.assertEqual(captured.records[0].levelno, logging.INFO)
        self.assertIn("SPEED_TRACKING", captured.records[0].getMessage())

    def test_a_readable_speed_logs_nothing(self):
        self._stub_properties({
            "MOUNT_TRACKING": self._tracking_on(),
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Ok"},
        })
        with self.assertNoLogs(self.LOGGER, level="INFO"):
            self.telescope._Telescope__retrieve_speed()

    def test_the_speed_log_does_not_silence_the_status_log(self):
        self._stub_properties({})
        self.telescope._Telescope__retrieve_speed()
        with self.assertLogs("crac_server.component.telescope.telescope", level="ERROR") as captured:
            self.telescope.status = TelescopeStatus.LOST
        self.assertEqual(len(captured.records), 1)
