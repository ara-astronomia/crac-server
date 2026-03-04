from datetime import datetime
import json
from typing import Any
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from crac_server.component.weather.weather import Weather


class TestWeather(unittest.TestCase):

    def retrieve(self):
        json = {
            "outTemp": {
                "value": "21,5",
                "unit_of_measurement": "°C"
            },
            "humidity": {
                "value": "55,5",
                "unit_of_measurement": "%"
            },
            "windSpeed": {
                "value": "2,6",
                "unit_of_measurement": "m/s"
            },
            "windGust": {
                "value": "4,2",
                "unit_of_measurement": "m/s"
            },
            "rainRate": {
                "value": "0",
                "unit_of_measurement": "mm/h"
            },
            "barometer": {
                "value": "1002",
                "unit_of_measurement": "mbar"
            },
            "barometerTrend": {
                "value": "-3",
                "unit_of_measurement": "mbar"
            }
        }
        updated_at = datetime.now().strftime(self.format)

        return json, updated_at
    
    def __to_expected(self, value: dict[str, Any]):
        return float(value["value"].replace(',','.')), value["unit_of_measurement"]

    def setUp(self) -> None:
        self.format = "%Y-%m-%d %H:%M:%S"
        self.url = "http://ara.test"
        self.fallback_url = "http://fallback.ara.test"
        self.weather = Weather(self.url, self.fallback_url, self.format, 600, 1200)

    def tearDown(self) -> None:
        del(self.weather, self.format, self.url, self.fallback_url)

    def test_is_expired(self):
        self.weather._retrieve_data = MagicMock(return_value=self.retrieve())    
        self.assertTrue(self.weather.is_expired(), "Is not Expired")
        self.weather.temperature
        self.assertFalse(self.weather.is_expired(), "Is Expired")

    def test_get_sensor(self):
        json = self.retrieve()[0]
        self.weather._retrieve_data = MagicMock(return_value=self.retrieve())
        self.assertEqual(self.__to_expected(json["outTemp"]), self.weather.temperature)
        self.assertEqual(self.__to_expected(json["humidity"]), self.weather.humidity)
        self.assertEqual(self.__to_expected(json["windSpeed"]), self.weather.wind_speed)
        self.assertEqual(self.__to_expected(json["windGust"]), self.weather.wind_gust_speed)
        self.assertEqual(self.__to_expected(json["rainRate"]), self.weather.rain_rate)
        self.assertEqual(self.__to_expected(json["barometer"]), self.weather.barometer)
        self.assertEqual(self.__to_expected(json["barometerTrend"]), self.weather.barometer_trend)
    
    def test_url_raise_error(self):
        json = self.retrieve()[0]
        self.weather._retrieve_data = MagicMock(side_effect=URLError(reason="url not found"))
        self.weather._retrieve_fallback_data = MagicMock(return_value=self.retrieve())
        self.assertEqual(self.__to_expected(json["outTemp"]), self.weather.temperature)
        self.assertEqual(self.__to_expected(json["humidity"]), self.weather.humidity)
        self.assertEqual(self.__to_expected(json["windSpeed"]), self.weather.wind_speed)
        self.assertEqual(self.__to_expected(json["windGust"]), self.weather.wind_gust_speed)
        self.assertEqual(self.__to_expected(json["rainRate"]), self.weather.rain_rate)
        self.assertEqual(self.__to_expected(json["barometer"]), self.weather.barometer)
        self.assertEqual(self.__to_expected(json["barometerTrend"]), self.weather.barometer_trend)
    
    @patch("urllib.request.urlopen")
    def test_urlopen(self, urlopen):
        urlopen.return_value = self.mocked_urlopen()
        json = self.retrieve()[0]
        self.weather.temperature
        self.assertEqual(self.__to_expected(json["outTemp"]), self.weather.temperature)

    @patch("urllib.request.urlopen")
    def test_fallback_urlopen(self, urlopen):
        urlopen.return_value = self.mocked_urlopen()
        self.weather._retrieve_data = MagicMock(side_effect=URLError(reason="url not found"))
        json = self.retrieve()[0]
        self.weather.temperature
        self.assertEqual(self.__to_expected(json["outTemp"]), self.weather.temperature)

    @patch("urllib.request.urlopen")
    def test_fallback_urlopen_in_error(self, urlopen):
        urlopen.return_value = self.mocked_urlopen_in_error()
        self.weather._retrieve_data = MagicMock(side_effect=URLError(reason="url not found"))
        self.assertRaises(URLError, self.weather._get_sensor, "outTemp")        

    def mocked_urlopen(self):
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

    def mocked_urlopen_in_error(self):
        current, time = self.retrieve()
        
        weather_station = {
            "current": current,
            "time": time
        }

        urlopen_read = MagicMock()
        urlopen_read.getcode.return_value = 400
        urlopen_read.read.side_effect = MagicMock(side_effect=URLError(reason="url not found"))
        urlopen_read.__enter__.return_value = urlopen_read

        return urlopen_read

    def test_url(self):
        self.assertEqual(self.weather.url, self.url)
        self.assertEqual(self.weather.fallback_url, self.fallback_url)
