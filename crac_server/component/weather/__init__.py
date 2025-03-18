from crac_server.component.weather.weather import Weather
from crac_server.config import Config


WEATHER = Weather(
    url=Config.getValue("url", "weather"),
    fallback_url=Config.getValue("fallback_url", "weather"),
    time_format=Config.getValue("time_format", "weather"),
    time_expired=Config.getInt("time_expired", "weather"),
    retry_interval=Config.getInt("retry_interval", "weather"),
)

#WEATHER.temperature # for warm up at start
