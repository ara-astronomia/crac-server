import unittest
from unittest.mock import patch

from crac_server.app import main


class TestMain(unittest.TestCase):

    def test_a_crash_hard_exits_instead_of_letting_atexit_release_the_pins(self):
        """A normal Python exit (even from an unhandled exception) runs
        gpiozero's atexit cleanup, which releases every GPIO pin - on this
        hardware that means driving the roof and the switches. A hard exit
        skips atexit entirely, leaving the pins as they are."""
        with patch("crac_server.app.asyncio.run", side_effect=RuntimeError("boom")):
            with patch("crac_server.app.os._exit") as mocked_exit:
                main()

        mocked_exit.assert_called_once_with(1)

    def test_a_clean_termination_does_not_hard_exit(self):
        with patch("crac_server.app.asyncio.run", return_value=None):
            with patch("crac_server.app.os._exit") as mocked_exit:
                main()

        mocked_exit.assert_not_called()
