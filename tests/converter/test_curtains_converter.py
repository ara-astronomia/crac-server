import unittest
from types import SimpleNamespace

from crac_protobuf.button_pb2 import ButtonKey
from crac_protobuf.curtains_pb2 import CurtainsAction, CurtainStatus
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

    def _button(self, status, is_disabled):
        mediator = SimpleNamespace(status_east=status, status_west=status, steps_east=0, steps_west=0, is_disabled=is_disabled)
        return CurtainsConverter().convert(mediator).buttons_gui[0]

    def test_disable_can_always_be_pressed(self):
        button = self._button(CurtainStatus.CURTAIN_STOPPED, is_disabled=True)

        self.assertEqual(CurtainsAction.DISABLE, button.metadata)
        self.assertFalse(button.is_disabled)

    def test_enable_is_greyed_out_when_the_curtains_cannot_be_enabled(self):
        button = self._button(CurtainStatus.CURTAIN_DISABLED, is_disabled=True)

        self.assertEqual(CurtainsAction.ENABLE, button.metadata)
        self.assertTrue(button.is_disabled)


if __name__ == "__main__":
    unittest.main()
