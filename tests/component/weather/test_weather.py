from datetime import datetime
import json
import unittest
from unittest.mock import MagicMock, patch
from crac_server.component.weather.weather import Weather


class TestWeather(unittest.TestCase):

    def retrieve(self):
        json = {
            "outTemp": {
                "value": self.input_temperature[0],
                "unit_of_measurement": self.input_temperature[1]
            },
            "humidity": {
                "value": self.input_humidity[0],
                "unit_of_measurement": self.input_humidity[1]
            },
            "windSpeed": {
                "value": self.input_wind_speed[0],
                "unit_of_measurement": self.input_wind_speed[1]
            },
            "windGust": {
                "value": self.input_wind_gust_speed[0],
                "unit_of_measurement": self.input_wind_gust_speed[1]
            },
            "rainRate": {
                "value": self.input_rain_rate[0],
                "unit_of_measurement": self.input_rain_rate[1]
            },
            "barometer": {
                "value": self.input_barometer[0],
                "unit_of_measurement": self.input_barometer[1]
            },
        }
        updated_at = datetime.now().strftime(self.format)

        return json, updated_at

    def mocked_urloped(self):
        current, time = self.retrieve()
        
        weather_station = {
            "current": current,
            "time": time
        }

        urlopen_read = MagicMock()
        urlopen_read.getcode.return_value = 200
        urlopen_read.read.return_value = json.dumps(weather_station).encode("utf8")
        urlopen_read.__enter__.return_value = urlopen_read

        return urlopen_read
    
    def __to_expected(self, value: list):
        return float(value[0].replace(',','.')), value[1]

    def setUp(self) -> None:
        self.format = "%Y-%m-%d %H:%M:%S"
        self.url = "http://ara.test"
        self.input_temperature = ("21,5", "°C")
        self.expected_temperature = self.__to_expected(self.input_temperature)

        self.input_humidity = ("55,5", "%")
        self.expected_humidity = self.__to_expected(self.input_humidity)

        self.input_wind_speed = ("8,6", "km/h")
        self.expected_wind_speed = self.__to_expected(self.input_wind_speed)

        self.input_wind_gust_speed = ("18,2", "km/h")
        self.expected_wind_gust_speed = self.__to_expected(self.input_wind_gust_speed)

        self.input_rain_rate = ("5,2", "mm/h")
        self.expected_rain_rate = self.__to_expected(self.input_rain_rate)

        self.input_barometer = ("1002", "mbar")
        self.expected_barometer = self.__to_expected(self.input_barometer)
    
    def tearDown(self) -> None:
        self.weather = None

    @patch('urllib.request.urlopen')
    def test_is_expired(self, mock_urlopen):
        mock_urlopen.return_value = self.mocked_urloped()
        
        weather = Weather(self.url, self.format, 600)
        self.assertTrue(weather.is_expired(), "Is not Expired")
        weather.temperature
        self.assertFalse(weather.is_expired(), "Is Expired")
        mock_urlopen.assert_called()

    @patch('urllib.request.urlopen')
    def test_get_sensor(self, mock_urlopen):
        mock_urlopen.return_value = self.mocked_urloped()

        weather = Weather(self.url, self.format, 600)
        self.assertEqual(self.expected_temperature, weather.temperature)
        self.assertEqual(self.expected_humidity, weather.humidity)
        self.assertEqual(self.expected_wind_speed, weather.wind_speed)
        self.assertEqual(self.expected_wind_gust_speed, weather.wind_gust_speed)
        self.assertEqual(self.expected_rain_rate, weather.rain_rate)
        self.assertEqual(self.expected_barometer, weather.barometer)
        mock_urlopen.assert_called()

    def test_url(self):
        weather = Weather(self.url, self.format, 600)
        self.assertEqual(weather.url, self.url)
