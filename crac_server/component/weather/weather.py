import config
import urllib.request, json 


class Weather:
    def __init__(self) -> None:
        self._url = config.Config.getValue("url", "weather")
        self._json : dict = None
    
    @property
    def url(self):
        return self._url

    def retrieve_data(self):
        with urllib.request.urlopen(self.url) as url:
            self._json = json.loads(url.read().decode())

    @property
    def json(self):
        return self._json

    @property
    def temperature(self):
        return float(self.json["current"]["outTemp"].replace(',','.'))

    @property
    def humidity(self):
        return float(self.json["current"]["humidity"].replace(',','.'))

    @property
    def wind_speed(self):
        return float(self.json["current"]["windSpeed"].replace(',','.'))

    @property
    def wind_gust_speed(self):
        return float(self.json["current"]["windGust"].replace(',','.'))

    @property
    def rain_rate(self):
        return float(self.json["current"]["rainRate"].replace(',','.'))

    @property
    def barometer(self):
        return float(self.json["current"]["barometer"].replace(',','.'))
