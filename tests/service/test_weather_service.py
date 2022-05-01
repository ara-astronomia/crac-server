import unittest
from unittest.mock import MagicMock, PropertyMock, patch
from crac_server.component.weather.weather import Weather
from crac_server.service.weather_service import WeatherService


class TestWeatherService(unittest.TestCase):

    def setUp(self):
        self.weather: Weather = MagicMock()
        self.weather_service = WeatherService(self.weather)
    
    @patch("crac_server.config.Config.getInt", return_value=5)
    def test_get_status(self, mock_config_int):
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

        response = self.weather_service.GetStatus(None, None)
        self.assertEqual((response.wind_speed.value, response.wind_speed.unit_of_measurement), self.weather.wind_speed)
        self.assertEqual((response.wind_gust_speed.value, response.wind_gust_speed.unit_of_measurement), self.weather.wind_gust_speed)
        self.assertEqual((response.humidity.value, response.humidity.unit_of_measurement), self.weather.humidity)
        self.assertEqual((response.temperature.value, response.temperature.unit_of_measurement), self.weather.temperature)
        self.assertEqual((response.rain_rate.value, response.rain_rate.unit_of_measurement), self.weather.rain_rate)
        self.assertEqual((response.barometer.value, response.barometer.unit_of_measurement), self.weather.barometer)
