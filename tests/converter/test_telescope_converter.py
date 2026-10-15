import unittest
from unittest.mock import MagicMock

from crac_protobuf.button_pb2 import ButtonKey, ButtonLabel
from crac_protobuf.telescope_pb2 import TelescopeAction, TelescopeSpeed, TelescopeStatus
from crac_server.converter.telescope_converter import TelescopeConverter


class TestTelescopeConverter(unittest.TestCase):

    def _convert(self, status):
        mediator = MagicMock()
        mediator.status = status
        mediator.speed = TelescopeSpeed.SPEED_NOT_TRACKING
        mediator.button.aa_coords = None
        mediator.button.eq_coords = None
        mediator.connect_is_disabled = mediator.park_is_disabled = mediator.flat_is_disabled = False
        return TelescopeConverter().convert(mediator)

    def _connection_button(self, status):
        return next(
            b for b in self._convert(status).buttons_gui
            if b.key == ButtonKey.KEY_TELESCOPE_CONNECTION_TOGGLE
        )

    def test_after_a_failed_movement_the_telescope_is_still_connected(self):
        button = self._connection_button(TelescopeStatus.ERROR)
        self.assertEqual(button.label, ButtonLabel.LABEL_TELESCOPE_CONNECTED)
        self.assertEqual(button.metadata, TelescopeAction.TELESCOPE_DISCONNECT)
        self.assertEqual(button.button_color.background_color, "orange")

    def test_the_failed_movement_stays_in_the_status(self):
        self.assertEqual(self._convert(TelescopeStatus.ERROR).status, TelescopeStatus.ERROR)

    def test_a_lost_telescope_offers_to_connect(self):
        button = self._connection_button(TelescopeStatus.LOST)
        self.assertEqual(button.label, ButtonLabel.LABEL_TELESCOPE_DISCONNECTED)
        self.assertEqual(button.metadata, TelescopeAction.TELESCOPE_CONNECT)


if __name__ == "__main__":
    unittest.main()
