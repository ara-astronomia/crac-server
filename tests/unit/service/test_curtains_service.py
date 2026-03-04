import unittest
from unittest.mock import MagicMock, patch
from crac_protobuf.curtains_pb2 import (
    CurtainsAction,
    CurtainsRequest,
    CurtainStatus,
)
from crac_server.service.curtains_service import CurtainsService


class TestCurtainsService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.curtains_service = CurtainsService()

    @patch("crac_server.handler.curtains_handler.ROOF")
    @patch("crac_server.handler.curtains_handler.TELESCOPE")
    @patch("crac_server.handler.curtains_handler.WEATHER")
    @patch("crac_server.converter.curtains_converter.CURTAIN_EAST")
    @patch("crac_server.converter.curtains_converter.CURTAIN_WEST")
    async def test_set_action_enable(
        self,
        mock_curtain_west,
        mock_curtain_east,
        mock_weather,
        mock_telescope,
        mock_roof,
    ):
        mock_roof.get_status.return_value = MagicMock()
        mock_curtain_east.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_east.steps.return_value = 100
        mock_curtain_west.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_west.steps.return_value = 100

        request = CurtainsRequest(action=CurtainsAction.ENABLE)
        response = await self.curtains_service.SetAction(request, None)

        self.assertIsNotNone(response)
        self.assertEqual(len(response.curtains), 2)

    @patch("crac_server.handler.curtains_handler.ROOF")
    @patch("crac_server.handler.curtains_handler.TELESCOPE")
    @patch("crac_server.handler.curtains_handler.WEATHER")
    @patch("crac_server.converter.curtains_converter.CURTAIN_EAST")
    @patch("crac_server.converter.curtains_converter.CURTAIN_WEST")
    async def test_set_action_disable(
        self,
        mock_curtain_west,
        mock_curtain_east,
        mock_weather,
        mock_telescope,
        mock_roof,
    ):
        mock_roof.get_status.return_value = MagicMock()
        mock_curtain_east.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_east.steps.return_value = 100
        mock_curtain_east.enable = MagicMock()
        mock_curtain_east.disable = MagicMock()
        mock_curtain_west.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_west.steps.return_value = 100
        mock_curtain_west.enable = MagicMock()
        mock_curtain_west.disable = MagicMock()

        request = CurtainsRequest(action=CurtainsAction.DISABLE)
        response = await self.curtains_service.SetAction(request, None)

        self.assertIsNotNone(response)

    @patch("crac_server.handler.curtains_handler.ROOF")
    @patch("crac_server.handler.curtains_handler.TELESCOPE")
    @patch("crac_server.handler.curtains_handler.WEATHER")
    @patch("crac_server.converter.curtains_converter.CURTAIN_EAST")
    @patch("crac_server.converter.curtains_converter.CURTAIN_WEST")
    async def test_set_action_roof_not_opened(
        self,
        mock_curtain_west,
        mock_curtain_east,
        mock_weather,
        mock_telescope,
        mock_roof,
    ):
        from crac_protobuf.roof_pb2 import RoofStatus

        mock_roof.get_status.return_value = RoofStatus.ROOF_CLOSED
        mock_curtain_east.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_east.steps.return_value = 100
        mock_curtain_west.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_west.steps.return_value = 100

        request = CurtainsRequest(action=CurtainsAction.ENABLE)
        response = await self.curtains_service.SetAction(request, None)

        self.assertIsNotNone(response)
        self.assertTrue(response.buttons_gui[0].is_disabled)

    @patch("crac_server.handler.curtains_handler.ROOF")
    @patch("crac_server.handler.curtains_handler.TELESCOPE")
    @patch("crac_server.handler.curtains_handler.WEATHER")
    @patch("crac_server.converter.curtains_converter.CURTAIN_EAST")
    @patch("crac_server.converter.curtains_converter.CURTAIN_WEST")
    async def test_set_action_telescope_not_polling(
        self,
        mock_curtain_west,
        mock_curtain_east,
        mock_weather,
        mock_telescope,
        mock_roof,
    ):
        mock_roof.get_status.return_value = MagicMock()
        mock_telescope.polling = False
        mock_curtain_east.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_east.steps.return_value = 100
        mock_curtain_west.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_west.steps.return_value = 100

        request = CurtainsRequest(action=CurtainsAction.ENABLE)
        response = await self.curtains_service.SetAction(request, None)

        self.assertIsNotNone(response)
        self.assertTrue(response.buttons_gui[0].is_disabled)
