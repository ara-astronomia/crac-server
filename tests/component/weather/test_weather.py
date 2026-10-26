from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    def test_a_source_that_closes_with_the_last_byte_still_reads_whole(self, urlopen):
        current, time = self.retrieve()
        body = json.dumps({"current": current, "time": time}).encode("utf8")

        class ClosingResponse:
            """http.client closes the response as soon as the last byte
            of a Content-Length body is read: fp is None from then on."""

            def __init__(self, body):
                self._body = body
                self.fp = MagicMock()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, amount):
                if not self._body:
                    return b""
                chunk, self._body = self._body[:amount], self._body[amount:]
                if not self._body:
                    self.fp = None
                return chunk

        urlopen.return_value = ClosingResponse(body)
        self.weather.refresh()
        self.assertEqual(self.__to_expected(current["outTemp"]), self.weather.temperature)

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


class TestTheReadAgainstARealResponse(unittest.TestCase):
    """The read loop walks private internals of http.client: against a
    real response, with the endings that have broken it before."""

    def setUp(self) -> None:
        self.format = "%Y-%m-%d %H:%M:%S"
        self.body = json.dumps({
            "current": {"outTemp": {"value": "21,5", "unit_of_measurement": "C"}},
            "time": datetime.now().strftime(self.format),
        }).encode("utf8")

    def _weather_served_by(self, serve, url_timeout=10):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                serve(self)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/current.json"
        return Weather(url, url, self.format, 600, 1200, url_timeout=url_timeout)

    def test_a_content_length_body_reads_whole(self):
        def serve(request):
            request.send_response(200)
            request.send_header("Content-Length", str(len(self.body)))
            request.end_headers()
            request.wfile.write(self.body)

        weather = self._weather_served_by(serve)

        weather.refresh()

        self.assertEqual("21,5", weather.json["outTemp"]["value"])
        self.assertFalse(weather.is_expired())

    def test_a_chunked_body_reads_whole(self):
        def serve(request):
            request.send_response(200)
            request.send_header("Transfer-Encoding", "chunked")
            request.end_headers()
            for start in range(0, len(self.body), 7):
                chunk = self.body[start:start + 7]
                request.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
            request.wfile.write(b"0\r\n\r\n")

        weather = self._weather_served_by(serve)

        weather.refresh()

        self.assertEqual("21,5", weather.json["outTemp"]["value"])

    def test_a_body_cut_in_half_ends_as_a_failed_read(self):
        def serve(request):
            request.send_response(200)
            request.send_header("Content-Length", str(len(self.body) * 2))
            request.end_headers()
            request.wfile.write(self.body[:len(self.body) // 2])

        weather = self._weather_served_by(serve)

        with self.assertRaises(json.JSONDecodeError):
            weather.refresh()

    def test_a_trickling_source_hits_the_total_deadline(self):
        def serve(request):
            request.send_response(200)
            request.send_header("Content-Length", str(len(self.body)))
            request.end_headers()
            for byte in self.body:
                sleep(0.4)
                request.wfile.write(bytes([byte]))
                request.wfile.flush()

        weather = self._weather_served_by(serve, url_timeout=1)

        with self.assertRaises(TimeoutError):
            weather.refresh()


class TestTheReadingRhythm(unittest.TestCase):
    """What the source asks of the reader: no hammering while the data
    is still served or the retry has not waited its interval."""

    def _payload(self, time):
        return json.dumps({
            "current": {"outTemp": {"value": "21,5", "unit_of_measurement": "C"}},
            "time": time,
        }).encode("utf8")

    def _mocked_response(self, payload):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = [payload, b""]
        return response

    @patch("urllib.request.urlopen")
    def test_a_stale_but_successful_read_waits_for_the_retry_before_reading_again(self, urlopen):
        stale = (datetime.now() - timedelta(seconds=600 * 3 + 10)).strftime("%Y-%m-%d %H:%M:%S")
        urlopen.return_value = self._mocked_response(self._payload(stale))
        weather = Weather("http://ara.test", "http://fallback.ara.test", "%Y-%m-%d %H:%M:%S", 600, 1200, url_timeout=10)

        weather.refresh()

        self.assertIsNotNone(weather.last_attempt_at)
        self.assertTrue(weather.is_expired())
        reads = urlopen.call_count
        weather.refresh()
        self.assertEqual(reads, urlopen.call_count)

    @patch("urllib.request.urlopen")
    def test_a_failed_read_is_not_tried_again_until_the_retry_interval_passes(self, urlopen):
        urlopen.side_effect = URLError("down")
        weather = Weather("http://ara.test", "http://fallback.ara.test", "%Y-%m-%d %H:%M:%S", 600, 1200, url_timeout=10)

        with self.assertRaises(URLError):
            weather.refresh()

        self.assertEqual(2, urlopen.call_count)
        weather.refresh()
        self.assertEqual(2, urlopen.call_count)
        weather.last_attempt_at = datetime.now() - timedelta(seconds=1201)
        with self.assertRaises(URLError):
            weather.refresh()
        self.assertEqual(4, urlopen.call_count)
