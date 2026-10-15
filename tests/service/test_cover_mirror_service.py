import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from crac_protobuf.button_pb2 import ButtonStatus
from crac_protobuf.cover_mirror_pb2 import (
    CoverMirrorAction,
    CoverMirrorRequest,
    CoverMirrorStatus,
)
from crac_server.handler.cover_mirror_handler import _background_tasks
from crac_server.service.cover_mirror_service import CoverMirrorService


class TestCoverMirrorServiceWithTheTelescopePower(unittest.IsolatedAsyncioTestCase):
    """The whole request path: the telescope supply decides whether a command reaches INDIGO."""

    def setUp(self):
        self.cover = MagicMock(open=AsyncMock(), close=AsyncMock())
        self.cover.get_status.return_value = CoverMirrorStatus.COVER_MIRROR_CLOSED
        patcher = patch("crac_server.converter.cover_mirror_converter.cover_mirror", return_value=self.cover)
        patcher.start()
        self.addCleanup(patcher.stop)

    def power(self, status: ButtonStatus):
        return patch(
            "crac_server.handler.cover_mirror_handler.switches",
            return_value={"TELE_SWITCH": MagicMock(get_status=MagicMock(return_value=status))},
        )

    async def open_cover(self):
        response = await CoverMirrorService().SetAction(
            CoverMirrorRequest(action=CoverMirrorAction.OPEN_COVER_MIRROR), None
        )
        await self.wait_for_spawned_commands()
        return response

    async def wait_for_spawned_commands(self):
        for task in list(_background_tasks):
            await task

    async def test_with_the_telescope_off_no_command_reaches_the_cover(self):
        with self.power(ButtonStatus.OFF):
            response = await self.open_cover()

        self.cover.open.assert_not_called()
        self.assertIs(True, response.button_gui.is_disabled)

    async def test_with_the_telescope_on_the_command_reaches_the_cover(self):
        with self.power(ButtonStatus.ON):
            response = await self.open_cover()

        self.cover.open.assert_awaited_once_with()
        self.assertIs(False, response.button_gui.is_disabled)


if __name__ == "__main__":
    unittest.main()
