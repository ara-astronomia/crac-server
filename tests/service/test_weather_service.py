import asyncio
from datetime import datetime
import json
from pathlib import Path
import os
from threading import Event
from time import sleep
import unittest
from unittest.mock import MagicMock, PropertyMock, patch
from urllib.error import URLError
from crac_protobuf.emergency_closure_pb2 import (
    EmergencyClosure,  # type: ignore
    EmergencyClosureStatus,  # type: ignore
    EmergencyClosureTrigger,  # type: ignore
)
from crac_protobuf.chart_pb2 import (
    WeatherResponse,  # type: ignore
    WeatherStatus,  # type: ignore
)
from crac_server.converter.chart_config import ChartConfigError
from crac_server.component.weather import weather
from crac_server.component.weather.weather import Weather
from crac_server.service.weather_service import WeatherService

WEATHER = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER
WEATHER_UNAVAILABLE = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER_UNAVAILABLE


class TestWeatherService(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.weather_service = WeatherService()
    
    async def test_get_status(self):
        readings = {
            "wind_speed": (7, "km/h"),
            "wind_gust_speed": (12, "km/h"),
            "humidity": (70, "%"),
            "temperature": (27, "°C"),
            "rain_rate": (4, "mm/h"),
            "barometer": (1063, "mbar"),
            "barometer_trend": (-3, "mbar"),
        }
        for name, value in readings.items():
            patcher = patch.object(type(weather()), name, new_callable=PropertyMock, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

        response = await self.weather_service.GetStatus(None, None)
        for chart in response.charts:
            if chart.urn == "weather.chart.wind":
                wind_chart = chart
                self.assertEqual((wind_chart.value, wind_chart.unit_of_measurement), weather().wind_speed)  # type: ignore
            if chart.urn == "weather.chart.wind_gust":
                wind_gust_chart = chart
                self.assertEqual((wind_gust_chart.value, wind_gust_chart.unit_of_measurement), weather().wind_gust_speed)  # type: ignore
            if chart.urn == "weather.chart.humidity":
                humidity_chart = chart
                self.assertEqual((humidity_chart.value, humidity_chart.unit_of_measurement), weather().humidity)  # type: ignore
            if chart.urn == "weather.chart.temperature":
                temperature_chart = chart
                self.assertEqual((temperature_chart.value, temperature_chart.unit_of_measurement), weather().temperature)  # type: ignore
            if chart.urn == "weather.chart.rain_rate":
                rain_rate_chart = chart
                self.assertEqual((rain_rate_chart.value, rain_rate_chart.unit_of_measurement), weather().rain_rate)  # type: ignore
            if chart.urn == "weather.chart.barometer":
                barometer_chart = chart
                self.assertEqual((barometer_chart.value, barometer_chart.unit_of_measurement), weather().barometer)  # type: ignore            
            if chart.urn == "weather.chart.barometer_trend":
                barometer_trend_chart = chart
                self.assertEqual((barometer_trend_chart.value, barometer_trend_chart.unit_of_measurement), weather().barometer_trend)  # type: ignore


    async def test_retriever_raise_exception(self):
        self.weather_service.weather_converter.convert = MagicMock(side_effect=Exception())
        response = await self.weather_service.GetStatus(None, None)
        self.assertEqual(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, response.status)


class TestWeatherServiceReportsToTheEmergencyClosure(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        patcher = patch("crac_server.service.weather_service.emergency_closure")
        self.closure = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.closure.state.return_value = EmergencyClosure(
            status=EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_BLOCKED,
            triggers=[WEATHER],
        )
        self.service = WeatherService()
        self.service.weather_converter = MagicMock()

    async def test_danger_is_reported_as_critical(self):
        self.service.weather_converter.convert.return_value = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER)

        await self.service.GetStatus(None, None)

        self.closure.report.assert_called_once_with(WEATHER, True)

    async def test_a_known_weather_out_of_danger_is_reported_as_not_critical(self):
        for status in (WeatherStatus.WEATHER_STATUS_NORMAL, WeatherStatus.WEATHER_STATUS_WARNING):
            with self.subTest(status=status):
                self.closure.report.reset_mock()
                self.service.weather_converter.convert.return_value = WeatherResponse(status=status)

                await self.service.GetStatus(None, None)

                self.closure.report.assert_called_once_with(WEATHER, False)

    async def test_an_unknown_weather_reports_nothing(self):
        self.service.weather_converter.convert.side_effect = ConnectionError("weather station unreachable")

        await self.service.GetStatus(None, None)

        self.closure.report.assert_not_called()

    async def test_every_response_carries_the_closure_state(self):
        for reading in (WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL), ConnectionError("unreachable")):
            with self.subTest(reading=reading):
                self.service.weather_converter.convert.side_effect = [reading]

                response = await self.service.GetStatus(None, None)

                self.assertEqual(self.closure.state.return_value, response.emergency_closure)


class TestWeatherServiceNotifiesTheExternalConditions(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        patcher = patch("crac_server.service.weather_service.external_conditions")
        self.conditions = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.service = WeatherService()
        self.service.weather_converter = MagicMock()

    async def test_a_known_weather_is_available(self):
        for status in (
            WeatherStatus.WEATHER_STATUS_NORMAL,
            WeatherStatus.WEATHER_STATUS_WARNING,
            WeatherStatus.WEATHER_STATUS_DANGER,
        ):
            with self.subTest(status=WeatherStatus.Name(status)):
                self.service.weather_converter.convert.return_value = WeatherResponse(status=status)

                await self.service.GetStatus(None, None)

                self.conditions.note_availability.assert_called_once_with(WEATHER_UNAVAILABLE, True)
                self.conditions.note_availability.reset_mock()

    async def test_an_unknown_weather_is_not_available(self):
        self.service.weather_converter.convert.side_effect = ConnectionError("weather station unreachable")

        await self.service.GetStatus(None, None)

        self.conditions.note_availability.assert_called_once_with(WEATHER_UNAVAILABLE, False)


class TestWeatherServiceWatchesOnItsOwn(unittest.IsolatedAsyncioTestCase):
    """
    The safety decision must not depend on a client polling GetStatus: the
    service checks the weather by itself, and closes only what can be closed.
    """

    SERVICE_LOGGER = "crac_server.service.weather_service"

    def setUp(self):
        closure_patcher = patch("crac_server.service.weather_service.emergency_closure")
        self.closure = closure_patcher.start().return_value
        self.addCleanup(closure_patcher.stop)
        self.closure.state.return_value = EmergencyClosure()

        weather_patcher = patch("crac_server.service.weather_service.weather")
        self.weather_source = weather_patcher.start().return_value
        self.addCleanup(weather_patcher.stop)
        self.weather_source.is_expired.return_value = False

        self.service = WeatherService()
        self.service.check_interval = 0.01
        self.service.weather_converter = MagicMock()
        self.service.weather_converter.convert.return_value = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER)

    async def test_danger_is_reported_without_any_client(self):
        await self.__watch_until_checked(times=1)

        self.closure.report.assert_called_with(WEATHER, True)

    async def test_the_watch_is_what_refreshes_the_data(self):
        await self.__watch_until_checked(times=1)

        self.weather_source.refresh.assert_called()

    async def test_a_failed_refresh_is_logged_once_and_the_watch_goes_on(self):
        self.weather_source.refresh.side_effect = URLError("offline")
        self.weather_source.is_expired.return_value = True

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__watch_until_checked(times=2)

        self.assertGreaterEqual(self.weather_source.refresh.call_count, 2)
        self.assertEqual(1, len(captured.records))
        self.assertIn("URLError", captured.records[0].getMessage())
        self.assertIsNotNone(captured.records[0].exc_info)

    async def test_a_check_that_cannot_run_counts_as_data_that_does_not_arrive(self):
        conditions_patcher = patch("crac_server.service.weather_service.external_conditions")
        conditions = conditions_patcher.start().return_value
        self.addCleanup(conditions_patcher.stop)

        self.service.weather_converter.convert.side_effect = ChartConfigError("[wind_speed]: 'danger' is inverted")

        await self.__watch_until_checked(times=2)

        conditions.note_availability.assert_called_with(WEATHER_UNAVAILABLE, False)

    async def test_a_failed_check_is_logged_and_the_watch_goes_on(self):
        self.service.weather_converter.convert.side_effect = self.__config_error_then_danger()

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__watch_until_checked(times=2)

        self.assertIn("'danger' is inverted", captured.output[0])
        self.closure.report.assert_called_with(WEATHER, True)

    async def test_a_different_failure_in_the_watch_is_logged_too(self):
        self.service.weather_converter.convert.side_effect = ChartConfigError("[wind_speed]: 'danger' is inverted")
        self.closure.report.side_effect = KeyError("pin")

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__watch_until_checked(times=2)
            self.service.weather_converter.convert.side_effect = None
            await self.__watch_until_checked(times=self.service.weather_converter.convert.call_count + 2)

        messages = [record.getMessage() for record in captured.records]
        self.assertTrue(any("ChartConfigError" in message for message in messages))
        self.assertTrue(any("KeyError" in message for message in messages))
        self.assertIsNotNone(captured.records[0].exc_info)

    async def test_the_watch_says_when_it_starts_and_how_often_it_checks(self):
        with self.assertLogs(self.SERVICE_LOGGER, level="INFO") as captured:
            await self.__watch_until_checked(times=1)

        self.assertIn(str(self.service.check_interval), captured.records[0].getMessage())

    async def test_the_watch_waits_check_interval_between_two_checks(self):
        with patch("crac_server.service.weather_service.asyncio.sleep", side_effect=asyncio.CancelledError) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await self.service.watch()

        sleep.assert_awaited_once_with(self.service.check_interval)

    async def __watch_until_checked(self, times):
        """Run the watch until the given number of checks is over, which is
        when the next one starts reading."""
        task = asyncio.create_task(self.service.watch())
        try:
            async with asyncio.timeout(2):
                while self.service.weather_converter.convert.call_count <= times:
                    await asyncio.sleep(0.001)
        finally:
            task.cancel()

    def __config_error_then_danger(self):
        yield ChartConfigError("[wind_speed]: 'danger' is inverted")
        while True:
            yield WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER)


class TestOnlyTheWatchReadsTheNetwork(unittest.IsolatedAsyncioTestCase):
    """The handlers and GetStatus answer from the cached data: a slow or
    broken weather source must not hold their RPCs on the event loop."""

    def _patched_service(self):
        patcher = patch("crac_server.service.weather_service.weather")
        self.weather_source = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.weather_source.is_expired.return_value = False
        service = WeatherService()
        service.weather_converter = MagicMock()
        service.weather_converter.convert.return_value = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL)
        return service

    async def test_get_status_reads_only_the_cache(self):
        service = self._patched_service()

        await service.GetStatus(None, None)

        self.weather_source.refresh.assert_not_called()

    async def test_the_watch_refreshes_the_data_from_the_network(self):
        service = self._patched_service()
        refresh = asyncio.create_task(service._refresh())

        await refresh

        self.weather_source.refresh.assert_called_once()

    async def test_a_slow_refresh_does_not_block_the_other_rpcs(self):
        service = self._patched_service()
        refresh_started = Event()

        def slow_refresh():
            refresh_started.set()
            sleep(0.3)

        self.weather_source.refresh.side_effect = slow_refresh
        refresh = asyncio.create_task(service._refresh())
        while not refresh_started.is_set():
            await asyncio.sleep(0.001)

        before = asyncio.get_running_loop().time()
        await asyncio.sleep(0.05)

        self.assertLess(asyncio.get_running_loop().time() - before, 0.3)
        await refresh


class TestWeatherServiceCheckInterval(unittest.TestCase):

    def test_a_missing_check_interval_fails_at_startup(self):
        with patch("crac_server.service.weather_service.Config.getValue", return_value=""):
            with self.assertRaises(ValueError):
                WeatherService()

    def test_an_interval_that_is_not_a_number_of_at_least_30_seconds_fails_at_startup(self):
        for value in ("abc", "29.9", "0", "-5", "nan", "inf"):
            with self.subTest(check_interval=value):
                with patch.dict(os.environ, {"WEATHER_CHECK_INTERVAL": value}):
                    with self.assertRaises(ValueError):
                        WeatherService()

    def test_30_seconds_is_accepted(self):
        with patch.dict(os.environ, {"WEATHER_CHECK_INTERVAL": "30"}):
            self.assertEqual(30, WeatherService().check_interval)


class TestWeatherServiceStartupValidation(unittest.TestCase):

    def test_a_broken_chart_section_fails_at_startup(self):
        with patch(
            "crac_server.converter.weather_converter.build_chart_from_config",
            side_effect=ChartConfigError("[wind_speed]: broken"),
        ):
            with self.assertRaises(ChartConfigError):
                WeatherService()


class TestWeatherServiceKeepsConfigurationErrorsVisible(unittest.IsolatedAsyncioTestCase):
    """A misconfigured threshold reported as an unreadable weather hides a
    protection that is not running."""

    async def test_reraises_a_broken_chart_section_instead_of_reporting_unspecified(self):
        service = WeatherService()
        service.weather_converter = MagicMock()
        service.weather_converter.convert.side_effect = ChartConfigError("[wind_speed]: 'danger' is inverted")

        with self.assertRaises(ChartConfigError):
            await service.GetStatus(None, None)

    async def test_still_reports_unspecified_when_the_reading_fails(self):
        service = WeatherService()
        service.weather_converter = MagicMock()
        service.weather_converter.convert.side_effect = ConnectionError("weather station unreachable")

        response = await service.GetStatus(None, None)

        self.assertEqual(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, response.status)

    async def test_a_reading_that_keeps_failing_is_logged_once_and_so_is_its_recovery(self):
        service = WeatherService()
        service.weather_converter = MagicMock()
        service.weather_converter.convert.side_effect = [
            ConnectionError("weather station unreachable"),
            ConnectionError("weather station unreachable"),
            WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL),
        ]

        with (
            patch("crac_server.service.weather_service.weather") as weather,
            self.assertLogs("crac_server.service.weather_service", level="INFO") as captured,
        ):
            weather.return_value.is_expired.return_value = False
            for _ in range(3):
                await service.GetStatus(None, None)

        self.assertEqual(["ERROR", "INFO"], [record.levelname for record in captured.records])
        self.assertIn("weather station unreachable", captured.records[0].getMessage())
        self.assertIn("recovered", captured.records[1].getMessage())

    async def test_http_failures_are_logged_once_until_fresh_data_recovers(self):
        service = WeatherService()
        time_format = "%Y-%m-%d %H:%M:%S"
        source = Weather("http://primary.test", "http://fallback.test",
                         time_format, 600, 0, url_timeout=1)
        fixture = Path(__file__).resolve().parents[2] / "crac_server/static/meteo_mock.json"
        payload = json.loads(fixture.read_text())
        payload["time"] = datetime.now().strftime(time_format)

        def chunks():
            yield json.dumps(payload).encode()
            while True:
                yield b""

        http_response = MagicMock()
        http_response.__enter__.return_value.read.side_effect = chunks()

        with (
            patch("crac_server.service.weather_service.weather", return_value=source),
            patch("urllib.request.urlopen", side_effect=URLError("offline")) as urlopen,
            self.assertLogs("crac_server", level="INFO") as captured,
        ):
            for _ in range(3):
                response = await self.__read(service)
                self.assertEqual(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, response.status)
            self.assertEqual(6, urlopen.call_count)
            self.assertEqual(["ERROR"], [record.levelname for record in captured.records])
            self.assertIsNotNone(captured.records[0].exc_info)

            urlopen.side_effect = None
            urlopen.return_value = http_response
            for _ in range(2):
                response = await self.__read(service)
                self.assertEqual(WeatherStatus.WEATHER_STATUS_NORMAL, response.status)
            self.assertEqual(["ERROR", "INFO"], [record.levelname for record in captured.records])
            self.assertIn("recovered", captured.records[1].getMessage())

            source.updated_at = "2000-01-01 00:00:00"
            urlopen.side_effect = URLError("offline again")
            await self.__read(service)
            self.assertEqual(["ERROR", "INFO", "ERROR"],
                             [record.levelname for record in captured.records])

    async def __read(self, service):
        await service._refresh()
        return await service.check()

    async def test_stale_data_after_a_failure_is_not_a_recovery(self):
        """After a failed refresh the next readings use the cached data: they
        succeed, but the source is still down until fresh data arrives."""
        service = WeatherService()
        service.weather_converter = MagicMock()
        service.weather_converter.convert.side_effect = [
            ConnectionError("weather station unreachable"),
            WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL),
            WeatherResponse(status=WeatherStatus.WEATHER_STATUS_WARNING),
            WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL),
        ]

        with (
            patch("crac_server.service.weather_service.weather") as weather,
            self.assertLogs("crac_server.service.weather_service", level="INFO") as captured,
        ):
            weather.return_value.is_expired.side_effect = [True, True, False]
            for _ in range(3):
                await service.GetStatus(None, None)
            self.assertEqual(["ERROR"], [record.levelname for record in captured.records])

            await service.GetStatus(None, None)

        self.assertEqual(["ERROR", "INFO"], [record.levelname for record in captured.records])
        self.assertIn("recovered", captured.records[1].getMessage())

    async def test_a_reading_failure_keeps_its_traceback(self):
        service = WeatherService()
        service.weather_converter = MagicMock()
        service.weather_converter.convert.side_effect = KeyError("current")

        with self.assertLogs("crac_server.service.weather_service", level="ERROR") as captured:
            await service.GetStatus(None, None)

        self.assertIn("KeyError", captured.records[0].getMessage())
        self.assertIsNotNone(captured.records[0].exc_info)

    async def test_a_slow_reading_lets_the_other_rpcs_through(self):
        """The weather refreshes from a remote source: while that one stays
        silent, roof, telescope, curtains and UPS must keep answering."""
        service = WeatherService()
        service.weather_converter = MagicMock()
        service.weather_converter.convert = self.__slow_reading

        order = []

        async def weather_reading():
            await service.GetStatus(None, None)
            order.append("weather")

        async def other_rpc():
            await asyncio.sleep(0.05)
            order.append("other rpc")

        await asyncio.gather(weather_reading(), other_rpc())
        self.assertEqual(["other rpc", "weather"], order)

    def __slow_reading(self, weather):
        sleep(0.3)
        return WeatherResponse(status=WeatherStatus.WEATHER_STATUS_NORMAL)
