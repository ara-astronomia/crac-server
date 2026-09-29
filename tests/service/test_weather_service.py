import asyncio
import os
from threading import Thread
from time import sleep
import unittest
from unittest.mock import MagicMock, PropertyMock, patch
from gpiozero import Device
from crac_protobuf.button_pb2 import ButtonType  # type: ignore
from crac_protobuf.curtains_pb2 import CurtainStatus  # type: ignore
from crac_protobuf.roof_pb2 import RoofStatus  # type: ignore
from crac_protobuf.telescope_pb2 import TelescopeStatus  # type: ignore
from crac_protobuf.chart_pb2 import (
    WeatherResponse,  # type: ignore
    WeatherStatus,  # type: ignore
)
from crac_server.component.roof.simulator.roof_pins import simulated_roof
from crac_server.component.telescope import telescope
from crac_server.converter.chart_builder import UnreachableThresholdError
from crac_server.component.weather import weather
from crac_server.service.weather_service import WeatherService

class TestWeatherService(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.weather_service = WeatherService()
    
    async def test_get_status(self):
        wind_speed = PropertyMock(return_value=(7, "km/h"))
        type(weather()).wind_speed = wind_speed  # type: ignore
        wind_gust_speed = PropertyMock(return_value=(12, "km/h"))
        type(weather()).wind_gust_speed = wind_gust_speed  # type: ignore
        humidity = PropertyMock(return_value=(70, "%"))
        type(weather()).humidity = humidity  # type: ignore
        temperature = PropertyMock(return_value=(27, "°C"))
        type(weather()).temperature = temperature  # type: ignore
        rain_rate = PropertyMock(return_value=(4, "mm/h"))
        type(weather()).rain_rate = rain_rate  # type: ignore
        barometer = PropertyMock(return_value=(1063, "mbar"))
        type(weather()).barometer = barometer  # type: ignore
        barometer_trend = PropertyMock(return_value=(-3, "mbar"))
        type(weather()).barometer_trend = barometer_trend  # type: ignore

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

    async def test_status_danger_close_crac(self):
        self.weather_service.weather_converter.convert = MagicMock(return_value=WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER))
        type(telescope()).polling = True  # type: ignore
        self.weather_service._emergency_closure = MagicMock()
        with patch("crac_server.service.weather_service.roof") as roof:
            roof.return_value.get_status.return_value = RoofStatus.ROOF_OPENED
            await self.weather_service.GetStatus(None, None)
        self.weather_service._emergency_closure.assert_called_once()


class TestWeatherServiceWatchesOnItsOwn(unittest.IsolatedAsyncioTestCase):
    """
    The safety decision must not depend on a client polling GetStatus: the
    service checks the weather by itself, and closes only what can be closed.
    """

    SERVICE_LOGGER = "crac_server.service.weather_service"

    def setUp(self):
        roof_patcher = patch("crac_server.service.weather_service.roof")
        self.roof = roof_patcher.start().return_value
        self.addCleanup(roof_patcher.stop)
        self.roof.get_status.return_value = RoofStatus.ROOF_OPENED
        telescope_patcher = patch("crac_server.service.weather_service.telescope")
        telescope_patcher.start().return_value.polling = True
        self.addCleanup(telescope_patcher.stop)

        self.service = WeatherService()
        self.service.check_interval = 0.01
        self.service.weather_converter = MagicMock()
        self.service.weather_converter.convert.return_value = WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER)
        self.service._emergency_closure = MagicMock()

    async def test_danger_starts_the_closure_without_any_client(self):
        await self.__watch_until_checked(times=1)

        self.service._emergency_closure.assert_called_once()

    async def test_a_failed_check_is_logged_and_the_watch_goes_on(self):
        self.service.weather_converter.convert.side_effect = self.__unreachable_threshold_then_danger()

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__watch_until_checked(times=2)

        self.assertIn("DANGER band is unreachable", captured.output[0])
        self.service._emergency_closure.assert_called_once()

    async def test_the_watch_waits_check_interval_between_two_checks(self):
        with patch("crac_server.service.weather_service.asyncio.sleep", side_effect=asyncio.CancelledError) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await self.service.watch()

        sleep.assert_awaited_once_with(self.service.check_interval)

    async def test_a_closed_roof_needs_no_closure(self):
        self.roof.get_status.return_value = RoofStatus.ROOF_CLOSED

        await self.service.GetStatus(None, None)

        self.service._emergency_closure.assert_not_called()

    async def test_a_roof_in_error_may_be_open_and_is_closed(self):
        self.roof.get_status.return_value = RoofStatus.ROOF_ERROR

        await self.service.GetStatus(None, None)

        self.service._emergency_closure.assert_called_once()

    async def test_a_closure_in_progress_is_not_started_twice(self):
        self.service.t = MagicMock()

        await self.service.GetStatus(None, None)
        await self.__watch_until_checked(times=3)

        self.service._emergency_closure.assert_not_called()

    async def __watch_until_checked(self, times):
        """Run the watch until the given number of checks is over, which is
        when the next one starts reading, then wait for the closure thread
        they may have started."""
        task = asyncio.create_task(self.service.watch())
        try:
            async with asyncio.timeout(2):
                while self.service.weather_converter.convert.call_count <= times:
                    await asyncio.sleep(0.001)
        finally:
            task.cancel()
        if isinstance(self.service.t, Thread):
            self.service.t.join()

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

        with self.assertLogs("crac_server.service.weather_service", level="INFO") as captured:
            for _ in range(3):
                await service.GetStatus(None, None)

        self.assertEqual(["ERROR", "INFO"], [record.levelname for record in captured.records])
        self.assertIn("weather station unreachable", captured.records[0].getMessage())
        self.assertIn("recovered", captured.records[1].getMessage())

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


class TestWeatherServiceEmergencyClosureReachesTheRoof(unittest.IsolatedAsyncioTestCase):
    """
    The emergency closure runs in its own thread while the roof motor is
    driven from the event loop: the sequence is only useful if the roof
    really ends up closed, so these tests run its body instead of mocking it.
    """

    SERVICE_LOGGER = "crac_server.service.weather_service"

    def setUp(self):
        Device.pin_factory.reset()
        self.addCleanup(Device.pin_factory.reset)
        self.roof = simulated_roof(travel_seconds=0.1)
        self.telescope = MagicMock()
        self.telescope.status = TelescopeStatus.PARKED
        doubles = {
            "roof": self.roof,
            "telescope": self.telescope,
            "curtain_east": self.__disabled_curtain(),
            "curtain_west": self.__disabled_curtain(),
            "switches": {ButtonType.Name(ButtonType.TELE_SWITCH): MagicMock()},
        }
        for name, double in doubles.items():
            patcher = patch(f"crac_server.service.weather_service.{name}", return_value=double)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = WeatherService()

    async def test_the_roof_is_closed_when_the_sequence_is_over(self):
        await self.roof.open()

        await self.__run_emergency_closure()

        self.assertEqual(RoofStatus.ROOF_CLOSED, self.roof.get_status())

    async def test_a_roof_that_did_not_close_is_logged_as_an_error(self):
        await self.roof.open()
        self.roof.timeout = 0

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__run_emergency_closure()

        self.assertIn("roof", captured.records[0].getMessage().lower())

    async def test_a_failed_sequence_is_logged_and_does_not_disarm_the_next_closure(self):
        self.telescope.queue_park.side_effect = RuntimeError("telescope unreachable")
        self.service.t = MagicMock()

        with self.assertLogs(self.SERVICE_LOGGER, level="ERROR") as captured:
            await self.__run_emergency_closure()

        self.assertIn("telescope unreachable", captured.output[0])
        self.assertIsNone(self.service.t)

    async def __run_emergency_closure(self):
        await asyncio.to_thread(self.service._emergency_closure, asyncio.get_running_loop())

    def __disabled_curtain(self):
        curtain = MagicMock()
        curtain.get_status.return_value = CurtainStatus.CURTAIN_DISABLED
        return curtain
