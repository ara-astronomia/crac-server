import unittest
from unittest.mock import MagicMock, PropertyMock
from crac_server.component.weather import WEATHER
from crac_server.component.weather.weather import Weather
from crac_server.service.weather_service import WeatherService


class TestWeatherService(unittest.TestCase):

    def setUp(self):
        WEATHER = MagicMock()
        self.weather_service = WeatherService()
    
    def test_get_status(self):
        wind_speed = PropertyMock(return_value=(7, "km/h"))
        type(WEATHER).wind_speed = wind_speed
        wind_gust_speed = PropertyMock(return_value=(12, "km/h"))
        type(WEATHER).wind_gust_speed = wind_gust_speed
        humidity = PropertyMock(return_value=(70, "%"))
        type(WEATHER).humidity = humidity
        temperature = PropertyMock(return_value=(27, "°C"))
        type(WEATHER).temperature = temperature
        rain_rate = PropertyMock(return_value=(4, "mm/h"))
        type(WEATHER).rain_rate = rain_rate
        barometer = PropertyMock(return_value=(1063, "mbar"))
        type(WEATHER).barometer = barometer
        barometer_trend = PropertyMock(return_value=(-3, "mbar"))
        type(WEATHER).barometer_trend = barometer_trend

        response = self.weather_service.GetStatus(None, None)
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

        self.assertEqual((wind_chart.value, wind_chart.unit_of_measurement), WEATHER.wind_speed)
        self.assertEqual((wind_gust_chart.value, wind_gust_chart.unit_of_measurement), WEATHER.wind_gust_speed)
        self.assertEqual((humidity_chart.value, humidity_chart.unit_of_measurement), WEATHER.humidity)
        self.assertEqual((temperature_chart.value, temperature_chart.unit_of_measurement), WEATHER.temperature)
        self.assertEqual((rain_rate_chart.value, rain_rate_chart.unit_of_measurement), WEATHER.rain_rate)
        self.assertEqual((barometer_chart.value, barometer_chart.unit_of_measurement), WEATHER.barometer)                
        self.assertEqual((barometer_trend_chart.value, barometer_trend_chart.unit_of_measurement), WEATHER.barometer_trend)
