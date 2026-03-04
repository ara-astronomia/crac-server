import unittest
from unittest.mock import MagicMock, patch
from crac_protobuf.button_pb2 import ButtonStatus
from crac_protobuf.curtains_pb2 import (
    CurtainStatus,
    CurtainsAction,
    CurtainsRequest,
)
from crac_protobuf.roof_pb2 import (
    RoofStatus,
    RoofAction,
    RoofRequest,
)
from crac_server.converter.curtains_converter import CurtainsConverter, CurtainsMediator
from crac_server.converter.button_converter import ButtonConverter, ButtonMediator
from crac_server.converter.roof_converter import RoofConverter, RoofMediator


class TestCurtainsConverter(unittest.TestCase):
    @patch("crac_server.converter.curtains_converter.CURTAIN_EAST")
    @patch("crac_server.converter.curtains_converter.CURTAIN_WEST")
    def test_convert_both_enabled(self, mock_curtain_west, mock_curtain_east):
        mock_curtain_east.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_east.steps.return_value = 100
        mock_curtain_west.get_status.return_value = CurtainStatus.CURTAIN_OPENED
        mock_curtain_west.steps.return_value = 100

        request = CurtainsRequest(action=CurtainsAction.ENABLE)
        mediator = CurtainsMediator(request)
        converter = CurtainsConverter()

        response = converter.convert(mediator)

        self.assertEqual(len(response.curtains), 2)
        self.assertEqual(len(response.buttons_gui), 2)

    @patch("crac_server.converter.curtains_converter.CURTAIN_EAST")
    @patch("crac_server.converter.curtains_converter.CURTAIN_WEST")
    def test_convert_both_disabled(self, mock_curtain_west, mock_curtain_east):
        mock_curtain_east.get_status.return_value = CurtainStatus.CURTAIN_DISABLED
        mock_curtain_east.steps.return_value = 0
        mock_curtain_west.get_status.return_value = CurtainStatus.CURTAIN_DISABLED
        mock_curtain_west.steps.return_value = 0

        request = CurtainsRequest(action=CurtainsAction.ENABLE)
        mediator = CurtainsMediator(request)
        converter = CurtainsConverter()

        response = converter.convert(mediator)

        self.assertEqual(response.buttons_gui[0].metadata, CurtainsAction.ENABLE)


class TestButtonConverter(unittest.TestCase):
    @patch("crac_server.converter.button_converter.SWITCHES")
    def test_convert_button_on(self, mock_switches):
        from crac_protobuf.button_pb2 import ButtonAction, ButtonRequest, ButtonType

        mock_button = MagicMock()
        mock_button.get_status.return_value = ButtonStatus.ON
        mock_switches.__getitem__.return_value = mock_button

        request = ButtonRequest(
            action=ButtonAction.TURN_ON, type=ButtonType.TELE_SWITCH
        )
        mediator = ButtonMediator(request)
        converter = ButtonConverter()

        response = converter.convert(mediator)

        self.assertEqual(response.status, ButtonStatus.ON)

    @patch("crac_server.converter.button_converter.SWITCHES")
    def test_convert_button_off(self, mock_switches):
        from crac_protobuf.button_pb2 import ButtonAction, ButtonRequest, ButtonType

        mock_button = MagicMock()
        mock_button.get_status.return_value = ButtonStatus.OFF
        mock_switches.__getitem__.return_value = mock_button

        request = ButtonRequest(
            action=ButtonAction.TURN_OFF, type=ButtonType.TELE_SWITCH
        )
        mediator = ButtonMediator(request)
        converter = ButtonConverter()

        response = converter.convert(mediator)

        self.assertEqual(response.status, ButtonStatus.OFF)


class TestRoofConverter(unittest.TestCase):
    @patch("crac_server.converter.roof_converter.ROOF")
    def test_convert_roof_opened(self, mock_roof):
        mock_roof.get_status.return_value = RoofStatus.ROOF_OPENED

        request = RoofRequest(action=RoofAction.OPEN)
        mediator = RoofMediator(request)
        converter = RoofConverter()

        response = converter.convert(mediator)

        self.assertEqual(response.status, RoofStatus.ROOF_OPENED)

    @patch("crac_server.converter.roof_converter.ROOF")
    def test_convert_roof_closed(self, mock_roof):
        mock_roof.get_status.return_value = RoofStatus.ROOF_CLOSED

        request = RoofRequest(action=RoofAction.CLOSE)
        mediator = RoofMediator(request)
        converter = RoofConverter()

        response = converter.convert(mediator)

        self.assertEqual(response.status, RoofStatus.ROOF_CLOSED)

    @patch("crac_server.converter.roof_converter.ROOF")
    def test_convert_roof_error(self, mock_roof):
        mock_roof.get_status.return_value = RoofStatus.ROOF_ERROR

        request = RoofRequest(action=RoofAction.OPEN)
        mediator = RoofMediator(request)
        converter = RoofConverter()

        response = converter.convert(mediator)

        self.assertEqual(response.status, RoofStatus.ROOF_ERROR)
