from crac_protobuf.chart_pb2_grpc import WeatherServicer
from crac_protobuf.chart_pb2 import (
    WeatherRequest,
    WeatherResponse,
    Chart,
    Threshold,
)
from crac_server.component.weather.weather import Weather
from crac_server.config import Config


class WeatherService(WeatherServicer):

    def __init__(self, weather: Weather) -> None:
        self._weather = weather

    @property
    def weather(self):
        return self._weather

    def GetStatus(self, request: WeatherRequest, context) -> WeatherResponse:
        response = WeatherResponse(
            wind_speed=Chart(
                value=self.weather.wind_speed[0],
                title="Vento",
                unit_of_measurement=self.weather.wind_speed[1],
                thresholds=(
                    Threshold(
                        warning=Config.getInt("warning", "wind_speed"),
                        error=Config.getInt("error", "wind_speed"),
                        upper_bound=Config.getInt(
                            "upper_bound", "wind_speed"
                        ),
                        lower_bound=Config.getInt(
                            "lower_bound", "wind_speed"
                        ),
                    ),
                ),
            ),
            wind_gust_speed=Chart(
                value=self.weather.wind_gust_speed[0],
                title="Raffiche vento",
                unit_of_measurement=self.weather.wind_gust_speed[1],
                thresholds=(
                    Threshold(
                        warning=Config.getInt("warning", "wind_gust_speed"),
                        error=Config.getInt("error", "wind_gust_speed"),
                        upper_bound=Config.getInt(
                            "upper_bound", "wind_gust_speed"
                        ),
                        lower_bound=Config.getInt(
                            "lower_bound", "wind_gust_speed"
                        ),
                    ),
                ),
            ),
            temperature=Chart(
                value=self.weather.temperature[0],
                title="Temperatura",
                unit_of_measurement=self.weather.temperature[1],
                thresholds=(
                    Threshold(
                        warning=Config.getInt("warning", "temperature"),
                        error=Config.getInt("error", "temperature"),
                        upper_bound=Config.getInt(
                            "upper_bound", "temperature"
                        ),
                        lower_bound=Config.getInt(
                            "lower_bound", "temperature"
                        ),
                    ),
                ),
            ),
            humidity=Chart(
                value=self.weather.humidity[0],
                title="Umidità",
                unit_of_measurement=self.weather.humidity[1],
                thresholds=(
                    Threshold(
                        warning=Config.getInt("warning", "humidity"),
                        error=Config.getInt("error", "humidity"),
                        upper_bound=Config.getInt("upper_bound", "humidity"),
                        lower_bound=Config.getInt("lower_bound", "humidity"),
                    ),
                ),
            ),
            rain_rate=Chart(
                value=self.weather.rain_rate[0],
                title="Pioggia",
                unit_of_measurement=self.weather.rain_rate[1],
                thresholds=(
                    Threshold(
                        warning=Config.getInt("warning", "rain_rate"),
                        error=Config.getInt("error", "rain_rate"),
                        upper_bound=Config.getInt(
                            "upper_bound", "rain_rate"
                        ),
                        lower_bound=Config.getInt(
                            "lower_bound", "rain_rate"
                        ),
                    ),
                ),
            ),
            barometer=Chart(
                value=self.weather.barometer[0],
                title="Barometro",
                unit_of_measurement=self.weather.barometer[1],
                thresholds=(
                    Threshold(
                        warning=Config.getInt("warning", "barometer"),
                        error=Config.getInt("error", "barometer"),
                        upper_bound=Config.getInt(
                            "upper_bound", "barometer"
                        ),
                        lower_bound=Config.getInt(
                            "lower_bound", "barometer"
                        ),
                    ),
                ),
            ),
            updated_at=int(self.weather.updated_at.timestamp())
        )

        return response
