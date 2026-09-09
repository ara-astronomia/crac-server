import logging
import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.telescope_pb2 import TelescopeStatus
from crac_server.component.status_log import ErrorCause
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
