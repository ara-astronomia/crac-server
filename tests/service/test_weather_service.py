import asyncio
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
from crac_server.component.telescope import TELESCOPE
from crac_server.converter.chart_builder import UnreachableThresholdError
from crac_server.component.weather import WEATHER
from crac_server.service.weather_service import WeatherService

class TestWeatherService(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        WEATHER = MagicMock()
        self.weather_service = WeatherService()
    
    async def test_get_status(self):
        wind_speed = PropertyMock(return_value=(7, "km/h"))
        type(WEATHER).wind_speed = wind_speed  # type: ignore
        wind_gust_speed = PropertyMock(return_value=(12, "km/h"))
        type(WEATHER).wind_gust_speed = wind_gust_speed  # type: ignore
        humidity = PropertyMock(return_value=(70, "%"))
        type(WEATHER).humidity = humidity  # type: ignore
        temperature = PropertyMock(return_value=(27, "°C"))
        type(WEATHER).temperature = temperature  # type: ignore
        rain_rate = PropertyMock(return_value=(4, "mm/h"))
        type(WEATHER).rain_rate = rain_rate  # type: ignore
        barometer = PropertyMock(return_value=(1063, "mbar"))
        type(WEATHER).barometer = barometer  # type: ignore
        barometer_trend = PropertyMock(return_value=(-3, "mbar"))
        type(WEATHER).barometer_trend = barometer_trend  # type: ignore

        response = await self.weather_service.GetStatus(None, None)
        for chart in response.charts:
            if chart.urn == "weather.chart.wind":
                wind_chart = chart
                self.assertEqual((wind_chart.value, wind_chart.unit_of_measurement), WEATHER.wind_speed)  # type: ignore
            if chart.urn == "weather.chart.wind_gust":
                wind_gust_chart = chart
                self.assertEqual((wind_gust_chart.value, wind_gust_chart.unit_of_measurement), WEATHER.wind_gust_speed)  # type: ignore
            if chart.urn == "weather.chart.humidity":
                humidity_chart = chart
                self.assertEqual((humidity_chart.value, humidity_chart.unit_of_measurement), WEATHER.humidity)  # type: ignore
            if chart.urn == "weather.chart.temperature":
                temperature_chart = chart
                self.assertEqual((temperature_chart.value, temperature_chart.unit_of_measurement), WEATHER.temperature)  # type: ignore
            if chart.urn == "weather.chart.rain_rate":
                rain_rate_chart = chart
                self.assertEqual((rain_rate_chart.value, rain_rate_chart.unit_of_measurement), WEATHER.rain_rate)  # type: ignore
            if chart.urn == "weather.chart.barometer":
                barometer_chart = chart
                self.assertEqual((barometer_chart.value, barometer_chart.unit_of_measurement), WEATHER.barometer)  # type: ignore            
            if chart.urn == "weather.chart.barometer_trend":
                barometer_trend_chart = chart
                self.assertEqual((barometer_trend_chart.value, barometer_trend_chart.unit_of_measurement), WEATHER.barometer_trend)  # type: ignore


    async def test_retriever_raise_exception(self):
        self.weather_service.weather_converter.convert = MagicMock(side_effect=Exception())
        response = await self.weather_service.GetStatus(None, None)
        self.assertEqual(WeatherStatus.WEATHER_STATUS_UNSPECIFIED, response.status)

    async def test_status_danger_close_crac(self):
        self.weather_service.weather_converter.convert = MagicMock(return_value=WeatherResponse(status=WeatherStatus.WEATHER_STATUS_DANGER))
        type(TELESCOPE).polling = True  # type: ignore
        self.weather_service._emergency_closure = MagicMock()
        await self.weather_service.GetStatus(None, None)
        self.weather_service._emergency_closure.assert_called_once()


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
            "ROOF": self.roof,
            "TELESCOPE": self.telescope,
            "CURTAIN_EAST": self.__disabled_curtain(),
            "CURTAIN_WEST": self.__disabled_curtain(),
            "SWITCHES": {ButtonType.Name(ButtonType.TELE_SWITCH): MagicMock()},
        }
        for name, double in doubles.items():
            patcher = patch(f"crac_server.service.weather_service.{name}", double)
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
