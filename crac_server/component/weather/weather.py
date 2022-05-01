from datetime import datetime
import html
import urllib.request
import json


class Weather:
    def __init__(self, url: str, time_format: str, time_expired: int):
        self._url = url
        self._json = None
        self._updated_at = None
        self._time_format = time_format
        self._time_expired = time_expired

    @property
    def url(self):
        return self._url

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
        return self.__get_sensor("outTemp")

    @property
    def humidity(self):
        return self.__get_sensor("humidity")

    @property
    def wind_speed(self):
        return self.__get_sensor("windSpeed")

    @property
    def wind_gust_speed(self):
        return self.__get_sensor("windGust")

    @property
    def rain_rate(self):
        return self.__get_sensor("rainRate")

    @property
    def barometer(self):
        return self.__get_sensor("barometer")

    def is_expired(self):
        return not self.updated_at or (datetime.now() - self.updated_at).seconds >= self._time_expired

    def __retrieve_data(self):
        with urllib.request.urlopen(self.url) as url:
            json_result = json.loads(url.read().decode())
        
        return json_result["current"], json_result["time"]

    def __get_sensor(self, name: str) -> tuple[float, str]:
        if self.is_expired():
            self.json, self.updated_at = self.__retrieve_data()
        
        sensor = self.json[name]
        return float(sensor["value"].replace(',', '.')), html.unescape(sensor["unit_of_measurement"]).strip()
