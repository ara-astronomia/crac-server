import unittest
from unittest.mock import MagicMock

from crac_protobuf.cover_mirror_pb2 import (
    CoverMirrorAction,
    CoverMirrorStatus,
)
from crac_server.converter.cover_mirror_converter import CoverMirrorConverter


class TestCoverMirrorConverter(unittest.TestCase):

    def _mediator(self, status, commanded_action=CoverMirrorAction.COVER_MIRROR_DEFAULT_ACTION):
        mediator = MagicMock()
        mediator.status = status
        mediator.is_disabled = False
        mediator.button.get_commanded_action.return_value = commanded_action
        return mediator

    def _metadata(self, status, commanded_action=CoverMirrorAction.COVER_MIRROR_DEFAULT_ACTION):
        response = CoverMirrorConverter().convert(self._mediator(status, commanded_action))
        return response.button_gui.metadata

    def test_opened_offers_close(self):
        self.assertEqual(
            self._metadata(CoverMirrorStatus.COVER_MIRROR_OPENED),
            CoverMirrorAction.CLOSE_COVER_MIRROR,
        )

    def test_closed_offers_open(self):
        self.assertEqual(
            self._metadata(CoverMirrorStatus.COVER_MIRROR_CLOSED),
            CoverMirrorAction.OPEN_COVER_MIRROR,
        )

    def test_opening_offers_close(self):
        self.assertEqual(
            self._metadata(CoverMirrorStatus.COVER_MIRROR_OPENING),
            CoverMirrorAction.CLOSE_COVER_MIRROR,
        )

    def test_closing_offers_open(self):
        self.assertEqual(
            self._metadata(CoverMirrorStatus.COVER_MIRROR_CLOSING),
            CoverMirrorAction.OPEN_COVER_MIRROR,
        )

    def test_error_after_failed_close_offers_close_again(self):
        self.assertEqual(
            self._metadata(CoverMirrorStatus.COVER_MIRROR_ERROR, CoverMirrorAction.CLOSE_COVER_MIRROR),
            CoverMirrorAction.CLOSE_COVER_MIRROR,
        )

    def test_error_after_failed_open_offers_open_again(self):
        self.assertEqual(
            self._metadata(CoverMirrorStatus.COVER_MIRROR_ERROR, CoverMirrorAction.OPEN_COVER_MIRROR),
            CoverMirrorAction.OPEN_COVER_MIRROR,
        )

    def test_error_without_known_command_offers_open(self):
        self.assertEqual(
            self._metadata(CoverMirrorStatus.COVER_MIRROR_ERROR),
            CoverMirrorAction.OPEN_COVER_MIRROR,
        )

    def test_error_is_labelled_and_red(self):
        response = CoverMirrorConverter().convert(self._mediator(CoverMirrorStatus.COVER_MIRROR_ERROR))
        self.assertEqual(response.button_gui.button_color.background_color, "red")
        self.assertEqual(response.status, CoverMirrorStatus.COVER_MIRROR_ERROR)
