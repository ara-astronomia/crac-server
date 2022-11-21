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
                self.assertEqual((chart.value, chart.unit_of_measurement), self.weather.wind_speed)
            if chart.urn == "weather.chart.wind_gust":
                self.assertEqual((chart.value, chart.unit_of_measurement), self.weather.wind_gust_speed)
            if chart.urn == "weather.chart.humidity":
                self.assertEqual((chart.value, chart.unit_of_measurement), self.weather.humidity)
            if chart.urn == "weather.chart.temperature":
                self.assertEqual((chart.value, chart.unit_of_measurement), self.weather.temperature)
            if chart.urn == "weather.chart.rain_rate":
                self.assertEqual((chart.value, chart.unit_of_measurement), self.weather.rain_rate)
            if chart.urn == "weather.chart.barometer":
                self.assertEqual((chart.value, chart.unit_of_measurement), self.weather.barometer)                
            if chart.urn == "weather.chart.barometer_trend":
                self.assertEqual((chart.value, chart.unit_of_measurement), self.weather.barometer_trend)
