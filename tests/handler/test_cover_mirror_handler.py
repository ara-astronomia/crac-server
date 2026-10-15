import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from crac_protobuf.button_pb2 import ButtonStatus
from crac_protobuf.cover_mirror_pb2 import CoverMirrorAction, CoverMirrorStatus
from crac_server.handler.cover_mirror_handler import CoverMirrorSwitchHandler


def tele_switch(status: ButtonStatus):
    return patch(
        "crac_server.handler.cover_mirror_handler.switches",
        return_value={"TELE_SWITCH": MagicMock(get_status=MagicMock(return_value=status))},
    )


class TestCoverMirrorSwitchHandler(unittest.TestCase):
    """The cover is powered by the telescope supply: with it off, no command may pass."""

    def setUp(self):
        self.mediator = SimpleNamespace(
            action=CoverMirrorAction.OPEN_COVER_MIRROR,
            is_disabled=False,
            button=MagicMock(),
            status=CoverMirrorStatus.COVER_MIRROR_OPENED,
        )
        self.next_handler = MagicMock()
        self.handler = CoverMirrorSwitchHandler()
        self.handler.set_next(self.next_handler)

    def test_with_the_telescope_off_the_cover_is_disabled_and_the_chain_stops(self):
        with tele_switch(ButtonStatus.OFF), \
             patch("crac_server.handler.cover_mirror_handler.CoverMirrorConverter"):
            self.handler.handle(self.mediator)

        self.assertIs(True, self.mediator.is_disabled)
        self.next_handler.handle.assert_not_called()

    def test_with_the_telescope_off_the_cover_keeps_its_last_known_position(self):
        with tele_switch(ButtonStatus.OFF), \
             patch("crac_server.handler.cover_mirror_handler.CoverMirrorConverter"):
            self.handler.handle(self.mediator)

        self.assertIs(CoverMirrorStatus.COVER_MIRROR_OPENED, self.mediator.status)

    def test_with_the_telescope_on_the_command_goes_on_along_the_chain(self):
        with tele_switch(ButtonStatus.ON):
            self.handler.handle(self.mediator)

        self.assertIs(False, self.mediator.is_disabled)
        self.next_handler.handle.assert_called_once_with(self.mediator)


if __name__ == "__main__":
    unittest.main()
