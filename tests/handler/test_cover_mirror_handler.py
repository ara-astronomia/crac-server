import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from crac_protobuf.cover_mirror_pb2 import (
    CoverMirrorAction,
    CoverMirrorResponse,
    CoverMirrorStatus,
)
from crac_protobuf.button_pb2 import ButtonStatus
from crac_server.converter.cover_mirror_converter import CoverMirrorConverter
from crac_server.handler.cover_mirror_handler import (
    AbstractCoverMirrorHandler,
    CoverMirrorSwitchHandler,
)


class TestCoverMirrorSwitchHandler(unittest.TestCase):
    """
    When the telescope power switch is off, the mirror cover must not accept commands.
    This is the twin of TelescopeSwitchHandler for the cover mirror.
    """

    def _make_mediator(
        self,
        action: CoverMirrorAction = CoverMirrorAction.OPEN_COVER_MIRROR,
        tele_switch_status: ButtonStatus = ButtonStatus.ON,
    ) -> SimpleNamespace:
        """Factory for a fake mediator with all the attributes an handler needs."""
        return SimpleNamespace(
            action=action,
            is_disabled=False,
            button=MagicMock(),
            status=CoverMirrorStatus.COVER_MIRROR_CLOSED,
        )

    def _patch_switches(self, tele_switch_status: ButtonStatus):
        """Patch the global switches() function to return a fake TELE_SWITCH."""
        mock_switches = {
            "TELE_SWITCH": MagicMock(
                get_status=MagicMock(return_value=tele_switch_status)
            )
        }
        return patch(
            "crac_server.handler.cover_mirror_handler.switches",
            return_value=mock_switches,
        )

    def test_disables_cover_mirror_commands_when_telescope_power_is_off(self):
        """When TELE_SWITCH is OFF, commands must be disabled."""
        mediator = self._make_mediator(tele_switch_status=ButtonStatus.OFF)

        with self._patch_switches(ButtonStatus.OFF):
            CoverMirrorSwitchHandler().handle(mediator)

        self.assertIs(True, mediator.is_disabled)

    def test_keeps_cover_mirror_enabled_when_telescope_power_is_on(self):
        """When TELE_SWITCH is ON, commands must be enabled."""
        mediator = self._make_mediator(tele_switch_status=ButtonStatus.ON)

        with self._patch_switches(ButtonStatus.ON):
            CoverMirrorSwitchHandler().handle(mediator)

        self.assertIs(False, mediator.is_disabled)

    def test_disables_all_actions_when_power_off(self):
        """Both OPEN and CLOSE must be disabled when power is off."""
        for action in [
            CoverMirrorAction.OPEN_COVER_MIRROR,
            CoverMirrorAction.CLOSE_COVER_MIRROR,
        ]:
            with self.subTest(action=action):
                mediator = self._make_mediator(action=action, tele_switch_status=ButtonStatus.OFF)

                with self._patch_switches(ButtonStatus.OFF):
                    CoverMirrorSwitchHandler().handle(mediator)

                self.assertIs(True, mediator.is_disabled)


class TestCoverMirrorSwitchHandlerChain(unittest.TestCase):
    """
    CoverMirrorSwitchHandler must be the first in the chain, and must stop
    the chain when it disables commands.
    """

    def test_stops_chain_when_disabled(self):
        """When handler disables, next handler must not be called."""
        mediator = SimpleNamespace(
            action=CoverMirrorAction.OPEN_COVER_MIRROR,
            is_disabled=False,
            button=MagicMock(),
            status=CoverMirrorStatus.COVER_MIRROR_CLOSED,
        )

        next_handler = MagicMock()
        switch_handler = CoverMirrorSwitchHandler()
        switch_handler._next_handler = next_handler

        with patch(
            "crac_server.handler.cover_mirror_handler.switches",
            return_value={
                "TELE_SWITCH": MagicMock(get_status=MagicMock(return_value=ButtonStatus.OFF))
            },
        ):
            CoverMirrorSwitchHandler().handle(mediator)

        self.assertIs(True, mediator.is_disabled)
        next_handler.handle.assert_not_called()

    def test_continues_chain_when_enabled(self):
        """When handler does not disable, next handler must be called."""
        mediator = SimpleNamespace(
            action=CoverMirrorAction.OPEN_COVER_MIRROR,
            is_disabled=False,
            button=MagicMock(),
            status=CoverMirrorStatus.COVER_MIRROR_CLOSED,
        )

        next_handler = MagicMock(return_value=CoverMirrorResponse())
        switch_handler = CoverMirrorSwitchHandler()
        switch_handler._next_handler = next_handler

        with patch(
            "crac_server.handler.cover_mirror_handler.switches",
            return_value={
                "TELE_SWITCH": MagicMock(get_status=MagicMock(return_value=ButtonStatus.ON))
            },
        ):
            switch_handler.handle(mediator)

        self.assertIs(False, mediator.is_disabled)
        next_handler.handle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
