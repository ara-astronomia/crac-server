from datetime import datetime
from http.client import IncompleteRead
import json
from threading import Thread
from time import sleep
from typing import Any
import unittest
from unittest.mock import MagicMock, call, patch
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
        self.weather = Weather(self.url, self.fallback_url, self.format, 600, 1200, url_timeout=10)

    def tearDown(self) -> None:
        del(self.weather, self.format, self.url, self.fallback_url)

    def test_is_expired(self):
        self.weather._retrieve_data = MagicMock(return_value=self.retrieve())
        self.assertTrue(self.weather.is_expired(), "Is not Expired")
        self.weather.refresh()
        self.assertFalse(self.weather.is_expired(), "Is Expired")

    def test_get_sensor(self):
        json = self.retrieve()[0]
        self.weather._retrieve_data = MagicMock(return_value=self.retrieve())
        self.weather.refresh()
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
        self.weather.refresh()
        self.assertEqual(self.__to_expected(json["outTemp"]), self.weather.temperature)
        self.assertEqual(self.__to_expected(json["humidity"]), self.weather.humidity)
        self.assertEqual(self.__to_expected(json["windSpeed"]), self.weather.wind_speed)
        self.assertEqual(self.__to_expected(json["windGust"]), self.weather.wind_gust_speed)
        self.assertEqual(self.__to_expected(json["rainRate"]), self.weather.rain_rate)
        self.assertEqual(self.__to_expected(json["barometer"]), self.weather.barometer)
        self.assertEqual(self.__to_expected(json["barometerTrend"]), self.weather.barometer_trend)

    def test_any_error_of_the_primary_source_tries_the_fallback(self):
        errors = (
            IncompleteRead(b"partial"),
            ValueError("invalid json"),
            KeyError("current"),
        )
        for error in errors:
            with self.subTest(error=error):
                weather = Weather(self.url, self.fallback_url, self.format, 600, 1200, url_timeout=10)
                weather._retrieve_data = MagicMock(side_effect=error)
                weather._retrieve_fallback_data = MagicMock(return_value=self.retrieve())

                weather.refresh()

                weather._retrieve_fallback_data.assert_called_once()
                self.assertFalse(weather.is_expired())

    def test_any_error_of_the_fallback_updates_last_attempt_at(self):
        errors = (
            IncompleteRead(b"partial"),
            ValueError("invalid json"),
        )
        for error in errors:
            with self.subTest(error=error):
                weather = Weather(self.url, self.fallback_url, self.format, 600, 1200, url_timeout=10)
                with patch("urllib.request.urlopen", side_effect=lambda *args, **kwargs: self.broken_urlopen(error)) as urlopen:
                    with self.assertRaises(type(error)):
                        weather.refresh()
                    self.assertIsNotNone(weather.last_attempt_at)
                    self.assertFalse(weather.is_retriable())

                    weather.refresh()

                    self.assertEqual(2, urlopen.call_count)
    
    @patch("urllib.request.urlopen")
    def test_urlopen(self, urlopen):
        urlopen.return_value = self.mocked_urlopen()
        json = self.retrieve()[0]
        self.weather.refresh()
        self.assertEqual(self.__to_expected(json["outTemp"]), self.weather.temperature)

    @patch("urllib.request.urlopen")
    def test_fallback_urlopen(self, urlopen):
        urlopen.return_value = self.mocked_urlopen()
        self.weather._retrieve_data = MagicMock(side_effect=URLError(reason="url not found"))
        json = self.retrieve()[0]
        self.weather.refresh()
        self.assertEqual(self.__to_expected(json["outTemp"]), self.weather.temperature)

    @patch("urllib.request.urlopen")
    def test_fallback_urlopen_in_error(self, urlopen):
        urlopen.return_value = self.mocked_urlopen_in_error()
        self.weather._retrieve_data = MagicMock(side_effect=URLError(reason="url not found"))
        self.assertRaises(URLError, self.weather.refresh)        

    @patch("crac_server.component.weather.weather.time")
    @patch("urllib.request.urlopen")
    def test_a_source_that_trickles_bytes_stops_at_the_total_deadline(self, urlopen, time):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"{"
        urlopen.return_value = response
        time.monotonic.side_effect = [0, 4, 8, 12]

        with self.assertRaises(TimeoutError):
            self.weather._retrieve_data()

        response.read.assert_called_with(1)
        response.fp.raw._sock.settimeout.assert_has_calls([call(6), call(2)])

    @patch("urllib.request.urlopen")
    def test_the_reading_has_a_deadline(self, urlopen):
        urlopen.return_value = self.mocked_urlopen()
        self.weather.refresh()
        self.assertEqual(self.weather.url_timeout, urlopen.call_args.kwargs.get("timeout"))

    @patch("urllib.request.urlopen")
    def test_the_fallback_reading_has_a_deadline_too(self, urlopen):
        urlopen.return_value = self.mocked_urlopen()
        self.weather._retrieve_data = MagicMock(side_effect=URLError(reason="url not found"))
        self.weather.refresh()
        self.assertEqual(self.weather.url_timeout, urlopen.call_args.kwargs.get("timeout"))

    @patch("urllib.request.urlopen")
    def test_sensors_read_only_the_cache(self, urlopen):
        urlopen.return_value = self.mocked_urlopen()
        self.weather.refresh()
        self.weather.updated_at = "2000-01-01 00:00:00"

        self.weather.temperature
        self.weather.humidity

        urlopen.assert_called_once()

    def test_two_concurrent_refreshes_read_once(self):
        """The conversion now runs in a thread while the handler chains read
        the same object from the loop: two readings together must not hit the
        weather station twice."""
        readings = []

        def slow_reading():
            sleep(0.2)
            readings.append(1)
            return self.retrieve()

        self.weather._retrieve_data = slow_reading
        thread = Thread(target=self.weather.refresh)
        thread.start()
        self.weather.refresh()
        thread.join()
        self.assertEqual(1, len(readings))

    def mocked_urlopen(self):
        current, time = self.retrieve()
        
        weather_station = {
            "current": current,
            "time": time
        }

        urlopen_read = MagicMock()
        urlopen_read.getcode.return_value = 200
        urlopen_read.read.side_effect = [json.dumps(weather_station).encode("utf8"), b""]
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

    def broken_urlopen(self, error):
        urlopen_read = MagicMock()
        urlopen_read.__enter__.return_value = urlopen_read
        if isinstance(error, ValueError):
            urlopen_read.read.side_effect = [b"not a json", b""]
        else:
            urlopen_read.read.side_effect = error

        return urlopen_read

    def test_url(self):
        self.assertEqual(self.weather.url, self.url)
        self.assertEqual(self.weather.fallback_url, self.fallback_url)
