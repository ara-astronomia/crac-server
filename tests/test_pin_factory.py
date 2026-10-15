import gc
from threading import Thread
import unittest
from unittest.mock import patch

from gpiozero import Device, OutputDevice


class Holder:
    pass


class TestPinFactory(unittest.TestCase):

    def setUp(self):
        Device.pin_factory.reset()
        self.addCleanup(Device.pin_factory.reset)

    def test_a_device_collected_while_another_reserves_its_pins_does_not_hang(self):
        """gpiozero closes a collected device in __del__, which takes the
        reservation lock: if the collector runs while a new device holds it,
        a plain lock hangs the suite."""
        holder = Holder()
        holder.device = OutputDevice(17)
        holder.cycle = holder
        Device.pin_factory.reset()
        del holder
        board = type(Device.pin_factory.board_info)
        find_pin = board.find_pin

        def find_pin_while_collecting(board_info, name):
            gc.collect()
            return find_pin(board_info, name)

        with patch.object(board, "find_pin", find_pin_while_collecting):
            reserving = Thread(target=OutputDevice, args=(18,), daemon=True)
            reserving.start()
            reserving.join(timeout=5)

        self.assertFalse(reserving.is_alive())


if __name__ == "__main__":
    unittest.main()
