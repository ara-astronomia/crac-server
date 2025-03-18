from time import sleep
import unittest
from unittest.mock import MagicMock, PropertyMock
from crac_protobuf.chart_pb2 import (
    WeatherResponse,  # type: ignore
    WeatherStatus,  # type: ignore
)
from crac_server.component.telescope import TELESCOPE
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
            if chart.urn == "weather.chart.wind_gust":
                wind_gust_chart = chart
            if chart.urn == "weather.chart.humidity":
                humidity_chart = chart
            if chart.urn == "weather.chart.temperature":
                temperature_chart = chart
            if chart.urn == "weather.chart.rain_rate":
                rain_rate_chart = chart
            if chart.urn == "weather.chart.barometer":
                barometer_chart = chart
            if chart.urn == "weather.chart.barometer_trend":
                barometer_trend_chart = chart

        self.assertEqual((wind_chart.value, wind_chart.unit_of_measurement), WEATHER.wind_speed)  # type: ignore
        self.assertEqual((wind_gust_chart.value, wind_gust_chart.unit_of_measurement), WEATHER.wind_gust_speed)  # type: ignore
        self.assertEqual((humidity_chart.value, humidity_chart.unit_of_measurement), WEATHER.humidity)  # type: ignore
        self.assertEqual((temperature_chart.value, temperature_chart.unit_of_measurement), WEATHER.temperature)  # type: ignore
        self.assertEqual((rain_rate_chart.value, rain_rate_chart.unit_of_measurement), WEATHER.rain_rate)  # type: ignore
        self.assertEqual((barometer_chart.value, barometer_chart.unit_of_measurement), WEATHER.barometer)  # type: ignore            
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
