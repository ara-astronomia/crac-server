import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch, sentinel

from crac_server.app import main, serve


class TestMain(unittest.TestCase):

    def setUp(self):
        """asyncio.run is mocked, so serve() is too: a real coroutine would
        never be awaited."""
        serve_patch = patch(
            "crac_server.app.serve", new_callable=Mock,
            return_value=sentinel.serve_coroutine,
        )
        self.mocked_serve = serve_patch.start()
        self.addCleanup(serve_patch.stop)

    def test_a_crash_hard_exits_instead_of_letting_atexit_release_the_pins(self):
        """A normal Python exit (even from an unhandled exception) runs
        gpiozero's atexit cleanup, which releases every GPIO pin - on this
        hardware that means driving the roof and the switches. A hard exit
        skips atexit entirely, leaving the pins as they are."""
        with patch("crac_server.app.asyncio.run", side_effect=RuntimeError("boom")) as mocked_run:
            with patch("crac_server.app.os._exit") as mocked_exit:
                main()

        self.mocked_serve.assert_called_once_with()
        mocked_run.assert_called_once_with(sentinel.serve_coroutine)
        mocked_exit.assert_called_once_with(1)

    def test_a_clean_termination_does_not_hard_exit(self):
        with patch("crac_server.app.asyncio.run", return_value=None) as mocked_run:
            with patch("crac_server.app.os._exit") as mocked_exit:
                main()

        self.mocked_serve.assert_called_once_with()
        mocked_run.assert_called_once_with(sentinel.serve_coroutine)
        mocked_exit.assert_not_called()


class TestServe(unittest.IsolatedAsyncioTestCase):

    async def test_the_weather_is_watched_by_the_same_service_that_answers_the_clients(self):
        server = MagicMock(start=AsyncMock(), wait_for_termination=AsyncMock())
        with patch("crac_server.app.build_components"), \
                patch("crac_server.app.grpc.aio.server", return_value=server), \
                patch("crac_server.app.WeatherService") as weather_service, \
                patch("crac_server.app.add_WeatherServicer_to_server") as add_weather:
            weather_service.return_value.watch = AsyncMock()
            server.wait_for_termination.side_effect = self.__running_for_a_moment
            await serve()

        add_weather.assert_called_once_with(weather_service.return_value, server)
        weather_service.return_value.watch.assert_awaited_once_with()

    async def __running_for_a_moment(self):
        await asyncio.sleep(0.01)
