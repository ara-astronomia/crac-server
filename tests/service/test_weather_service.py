import unittest
from unittest.mock import MagicMock, PropertyMock, patch
from crac_server.component.weather.weather import Weather
from crac_server.service.weather_service import WeatherService


class TestWeatherService(unittest.TestCase):

    def setUp(self):
        self.weather: Weather = MagicMock()
        self.weather_service = WeatherService(self.weather)
    
    def test_get_status(self):
        wind_speed = PropertyMock(return_value=(7, "km/h"))
        type(self.weather).wind_speed = wind_speed
        wind_gust_speed = PropertyMock(return_value=(12, "km/h"))
        type(self.weather).wind_gust_speed = wind_gust_speed
        humidity = PropertyMock(return_value=(70, "%"))
        type(self.weather).humidity = humidity
        temperature = PropertyMock(return_value=(27, "°C"))
        type(self.weather).temperature = temperature
        rain_rate = PropertyMock(return_value=(4, "mm/h"))
        type(self.weather).rain_rate = rain_rate
        barometer = PropertyMock(return_value=(1063, "mbar"))
        type(self.weather).barometer = barometer
        barometer_trend = PropertyMock(return_value=(-3, "mbar"))
        type(self.weather).barometer_trend = barometer_trend

        response = self.weather_service.GetStatus(None, None)
        for chart in response.charts:
            if chart.urn == "weather.chart.wind":
                wind = chart
            if chart.urn == "weather.chart.wind_gust":
                wind_gust = chart
            if chart.urn == "weather.chart.humidity":
                humidity = chart
            if chart.urn == "weather.chart.temperature":
                temperature = chart
            if chart.urn == "weather.chart.rain_rate":
                rain_rate = chart
            if chart.urn == "weather.chart.barometer":
                barometer = chart
            if chart.urn == "weather.chart.barometer_trend":
                barometer_trend = chart

        self.assertEqual((wind.value, wind.unit_of_measurement), self.weather.wind_speed)
        self.assertEqual((wind_gust.value, wind_gust.unit_of_measurement), self.weather.wind_gust_speed)
        self.assertEqual((humidity.value, humidity.unit_of_measurement), self.weather.humidity)
        self.assertEqual((temperature.value, temperature.unit_of_measurement), self.weather.temperature)
        self.assertEqual((rain_rate.value, rain_rate.unit_of_measurement), self.weather.rain_rate)
        self.assertEqual((barometer.value, barometer.unit_of_measurement), self.weather.barometer)                
        self.assertEqual((barometer_trend.value, barometer_trend.unit_of_measurement), self.weather.barometer_trend)
