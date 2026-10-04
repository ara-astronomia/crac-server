import unittest
from types import SimpleNamespace

from crac_protobuf.button_pb2 import ButtonKey
from crac_protobuf.curtains_pb2 import CurtainStatus
from crac_server.converter.curtains_converter import CurtainsConverter


class TestCurtainsConverter(unittest.TestCase):

    def test_the_only_curtains_button_is_enable_or_disable(self):
        mediator = SimpleNamespace(
            status_east=CurtainStatus.CURTAIN_OPENED,
            status_west=CurtainStatus.CURTAIN_OPENED,
            steps_east=100,
            steps_west=100,
            is_disabled=False,
        )

        response = CurtainsConverter().convert(mediator)

        self.assertEqual([ButtonKey.KEY_CURTAINS], [button.key for button in response.buttons_gui])


if __name__ == "__main__":
    unittest.main()
