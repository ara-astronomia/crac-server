from crac_server.component.weather.weather import Weather
from crac_server.config import Config


WEATHER = Weather(
    Config.getValue("url", "weather"),
    Config.getValue("time_format", "weather"),
    Config.getInt("time_expired", "weather"),
)
