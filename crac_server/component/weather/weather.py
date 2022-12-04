from datetime import datetime
import html
import logging
from typing import Union
from urllib.error import HTTPError, URLError
import urllib.request
import json


logger = logging.getLogger(__name__)


class Weather:
    def __init__(self, url: str, fallback_url: str, time_format: str, time_expired: int):
        self._url = url
        self._fallback_url = fallback_url
        self._json : dict
        self._updated_at : Union[datetime, None] = None
        self._time_format = time_format
        self._time_expired = time_expired

    @property
    def url(self):
        return self._url

    @property
    def fallback_url(self):
        return self._fallback_url

    @property
    def updated_at(self):
        return self._updated_at

    @updated_at.setter
    def updated_at(self, value: str):
        self._updated_at = datetime.strptime(value, self._time_format)

    @property
    def json(self):
        return self._json

    @json.setter
    def json(self, value):
        self._json = value

    @property
    def temperature(self):
        return self._get_sensor("outTemp")

    @property
    def humidity(self):
        return self._get_sensor("humidity")

    @property
    def wind_speed(self):
        return self._get_sensor("windSpeed")

    @property
    def wind_gust_speed(self):
        return self._get_sensor("windGust")

    @property
    def rain_rate(self):
        return self._get_sensor("rainRate")

    @property
    def barometer(self):
        return self._get_sensor("barometer")
    
    @property
    def barometer_trend(self):
        return self._get_sensor("barometerTrend")
    
    @property
    def time_expired(self) -> int:
        return self._time_expired

    def is_expired(self) -> bool:
        return not self.updated_at or (datetime.now() - self.updated_at).seconds >= self._time_expired
    
    @property
    def is_unavailable(self) -> bool:
        return self.updated_at != None and (datetime.now() - self.updated_at).seconds >= self._time_expired * 3

    def _retrieve_data(self):
        with urllib.request.urlopen(self.url) as url:
            json_result = json.loads(url.read().decode())
        
        return json_result["current"], json_result["time"]

    def _retrieve_fallback_data(self):
        try:
            with urllib.request.urlopen(self.fallback_url) as url:
                json_result = json.loads(url.read().decode())
            
            return json_result["current"], json_result["time"]
        except (HTTPError, URLError, TimeoutError) as error:
            logger.error("Fallback url in error")
            raise error


    def _get_sensor(self, name: str) -> tuple[float, str]:
        if self.is_expired():
            try:
                self.json, self.updated_at = self._retrieve_data()
            except (HTTPError, URLError, TimeoutError) as error:
                logger.error("url in error")
                self.json, self.updated_at = self._retrieve_fallback_data()
        
        sensor = self.json[name]
        return float(sensor["value"].replace(',', '.')), html.unescape(sensor["unit_of_measurement"]).strip()
