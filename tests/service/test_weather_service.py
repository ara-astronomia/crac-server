import asyncio
from datetime import datetime
import json
from pathlib import Path
import os
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
from crac_server.converter.chart_builder import UnreachableThresholdError
from crac_server.component.weather import weather
from crac_server.component.weather.weather import Weather
from crac_server.service.weather_service import WeatherService

WEATHER = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER


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

        self.service = WeatherService()
        self.service.check_interval = 0.01
        self.service.weather_converter = MagicMock()
        self.service.weather_converter.convert.return_value = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER)

    async def test_danger_is_reported_without_any_client(self):
        await self.__watch_until_checked(times=1)

        self.closure.report.assert_called_with(WEATHER, True)

    async def test_a_failed_check_is_logged_and_the_watch_goes_on(self):
        self.service.weather_converter.convert.side_effect = self.__unreachable_threshold_then_danger()

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__watch_until_checked(times=2)

        self.assertIn("DANGER band is unreachable", captured.output[0])
        self.closure.report.assert_called_with(WEATHER, True)

    async def test_a_different_failure_in_the_watch_is_logged_too(self):
        self.service.weather_converter.convert.side_effect = UnreachableThresholdError("DANGER band unreachable")
        self.closure.report.side_effect = KeyError("pin")

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__watch_until_checked(times=2)
            self.service.weather_converter.convert.side_effect = None
            await self.__watch_until_checked(times=self.service.weather_converter.convert.call_count + 2)

        messages = [record.getMessage() for record in captured.records]
        self.assertTrue(any("UnreachableThresholdError" in message for message in messages))
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

    def __unreachable_threshold_then_danger(self):
        yield UnreachableThresholdError("weather.chart.wind: the DANGER band is unreachable")
        while True:
            yield WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER)


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


class TestWeatherServiceKeepsConfigurationErrorsVisible(unittest.IsolatedAsyncioTestCase):
    """
    A weather reading that fails is reported as UNSPECIFIED, which is honest:
    the data is not there. A misconfigured threshold is a different thing, and
    reporting it the same way hides a protection that is not running.
    """

    async def test_reraises_an_unreachable_threshold_instead_of_reporting_unspecified(self):
        service = WeatherService()
        service.weather_converter = MagicMock()
        service.weather_converter.convert.side_effect = UnreachableThresholdError(
            "weather.chart.wind: the DANGER band is unreachable"
        )

        with self.assertRaises(UnreachableThresholdError):
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
        http_response = MagicMock()
        http_response.__enter__.return_value.read.return_value = json.dumps(payload).encode()

        with (
            patch("crac_server.service.weather_service.weather", return_value=source),
            patch("urllib.request.urlopen", side_effect=URLError("offline")) as urlopen,
            self.assertLogs("crac_server", level="INFO") as captured,
        ):
            for _ in range(3):
                response = await service.check()
                self.assertEqual(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, response.status)
            self.assertEqual(6, urlopen.call_count)
            self.assertEqual(["ERROR"], [record.levelname for record in captured.records])
            self.assertIsNotNone(captured.records[0].exc_info)

            urlopen.side_effect = None
            urlopen.return_value = http_response
            for _ in range(2):
                response = await service.check()
                self.assertEqual(WeatherStatus.WEATHER_STATUS_NORMAL, response.status)
            self.assertEqual(["ERROR", "INFO"], [record.levelname for record in captured.records])
            self.assertIn("recovered", captured.records[1].getMessage())

            source.updated_at = "2000-01-01 00:00:00"
            urlopen.side_effect = URLError("offline again")
            await service.check()
            self.assertEqual(["ERROR", "INFO", "ERROR"],
                             [record.levelname for record in captured.records])

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
