import logging
import unittest

from crac_protobuf.roof_pb2 import RoofStatus
from crac_server.component.status_log import ErrorCause, StatusLogger


class TestStatusLogger(unittest.TestCase):

    def setUp(self):
        self.logger = logging.getLogger("test_status_log")
        self.status_log = StatusLogger(self.logger, "Roof", RoofStatus)

    def test_error_is_logged_once_with_component_and_cause(self):
        with self.assertLogs(self.logger, level="ERROR") as captured:
            self.status_log.record(RoofStatus.ROOF_ERROR, ErrorCause.SENSORS_INCONSISTENT)
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("[Roof]", message)
        self.assertIn("ROOF_ERROR", message)
        self.assertIn(ErrorCause.SENSORS_INCONSISTENT, message)

    def test_same_error_repeated_is_not_logged_again(self):
        with self.assertLogs(self.logger, level="ERROR") as captured:
            self.status_log.record(RoofStatus.ROOF_ERROR, ErrorCause.SENSORS_INCONSISTENT)
            self.status_log.record(RoofStatus.ROOF_ERROR, ErrorCause.SENSORS_INCONSISTENT)
            self.status_log.record(RoofStatus.ROOF_ERROR, ErrorCause.SENSORS_INCONSISTENT)
        self.assertEqual(len(captured.records), 1)

    def test_a_different_cause_on_the_same_status_is_logged(self):
        with self.assertLogs(self.logger, level="ERROR") as captured:
            self.status_log.record(RoofStatus.ROOF_ERROR, ErrorCause.SENSORS_INCONSISTENT)
            self.status_log.record(RoofStatus.ROOF_ERROR, ErrorCause.BLOCKED_BY_SAFETY)
        self.assertEqual(len(captured.records), 2)
        self.assertIn(ErrorCause.BLOCKED_BY_SAFETY, captured.records[1].getMessage())

    def test_recovery_is_logged_at_info(self):
        self.status_log.record(RoofStatus.ROOF_ERROR, ErrorCause.SENSORS_INCONSISTENT)
        with self.assertLogs(self.logger, level="INFO") as captured:
            self.status_log.record(RoofStatus.ROOF_CLOSED)
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)
        self.assertIn("[Roof]", captured.records[0].getMessage())
        self.assertIn("ROOF_CLOSED", captured.records[0].getMessage())

    def test_healthy_readings_are_not_logged(self):
        self.logger.addHandler(logging.NullHandler())
        with self.assertNoLogs(self.logger, level="INFO"):
            self.status_log.record(RoofStatus.ROOF_CLOSED)
            self.status_log.record(RoofStatus.ROOF_OPENING)
            self.status_log.record(RoofStatus.ROOF_OPENED)

    def test_recovery_is_logged_only_once(self):
        self.status_log.record(RoofStatus.ROOF_ERROR, ErrorCause.SENSORS_INCONSISTENT)
        with self.assertLogs(self.logger, level="INFO") as captured:
            self.status_log.record(RoofStatus.ROOF_CLOSED)
            self.status_log.record(RoofStatus.ROOF_CLOSED)
            self.status_log.record(RoofStatus.ROOF_OPENED)
        self.assertEqual(len(captured.records), 1)

    def test_detail_is_appended_when_given(self):
        with self.assertLogs(self.logger, level="ERROR") as captured:
            self.status_log.record(
                RoofStatus.ROOF_ERROR,
                ErrorCause.SENSORS_INCONSISTENT,
                detail="open=True closed=True",
            )
        self.assertIn("open=True closed=True", captured.records[0].getMessage())
