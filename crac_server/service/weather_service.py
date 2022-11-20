from crac_protobuf.chart_pb2_grpc import WeatherServicer
from crac_protobuf.chart_pb2 import (
    WeatherRequest,
    WeatherResponse,
    Chart,
    Threshold,
    ThresholdType,
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
                min=Config.getInt("lower_bound", "wind_speed"),
                max=Config.getInt("upper_bound", "wind_speed"),
                unit_of_measurement=self.weather.wind_speed[1],
                thresholds=(
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_NORMAL,
                        upper_bound=Config.getInt(
                            "warning", "wind_speed"
                        ),
                        lower_bound=Config.getInt("lower_bound", "wind_speed"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                        upper_bound=Config.getInt(
                            "error", "wind_speed"
                        ),
                        lower_bound=Config.getInt("warning", "wind_speed"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_DANGER,
                        upper_bound=Config.getInt(
                            "upper_bound", "wind_speed"
                        ),
                        lower_bound=Config.getInt("error", "wind_speed"),
                    ),
                ),
            ),
            wind_gust_speed=Chart(
                value=self.weather.wind_gust_speed[0],
                title="Raffiche vento",
                min=Config.getInt("lower_bound", "wind_gust_speed"),
                max=Config.getInt("upper_bound", "wind_gust_speed"),
                unit_of_measurement=self.weather.wind_gust_speed[1],
                thresholds=(
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_NORMAL,
                        lower_bound=Config.getInt("lower_bound", "wind_gust_speed"),
                        upper_bound=Config.getInt("warning", "wind_gust_speed"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                        lower_bound=Config.getInt("warning", "wind_gust_speed"),
                        upper_bound=Config.getInt("error", "wind_gust_speed"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_DANGER,
                        lower_bound=Config.getInt("error", "wind_gust_speed"),
                        upper_bound=Config.getInt("upper_bound", "wind_gust_speed"),
                    ),
                ),
            ),
            temperature=Chart(
                value=self.weather.temperature[0],
                title="Temperatura",
                min=Config.getInt("lower_bound", "temperature"),
                max=Config.getInt("upper_bound", "temperature"),
                unit_of_measurement=self.weather.temperature[1],
                thresholds=(
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_NORMAL,
                        lower_bound=Config.getInt("lower_bound", "temperature"),
                        upper_bound=Config.getInt("warning", "temperature"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                        lower_bound=Config.getInt("warning", "temperature"),
                        upper_bound=Config.getInt("upper_bound", "temperature"),
                    ),
                ),
            ),
            humidity=Chart(
                value=self.weather.humidity[0],
                title="Umidità",
                min=Config.getInt("lower_bound", "humidity"),
                max=Config.getInt("upper_bound", "humidity"),
                unit_of_measurement=self.weather.humidity[1],
                thresholds=(
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_NORMAL,
                        upper_bound=Config.getInt("warning", "humidity"),
                        lower_bound=Config.getInt("lower_bound", "humidity"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                        lower_bound=Config.getInt("warning", "humidity"),
                        upper_bound=Config.getInt("error", "humidity"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_DANGER,
                        lower_bound=Config.getInt("error", "humidity"),
                        upper_bound=Config.getInt("upper_bound", "humidity"),
                    ),
                ),
            ),
            rain_rate=Chart(
                value=self.weather.rain_rate[0],
                title="Pioggia",
                min=Config.getInt("lower_bound", "rain_rate"),
                max=Config.getInt("upper_bound", "rain_rate"),
                unit_of_measurement=self.weather.rain_rate[1],
                thresholds=(
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_NORMAL,
                        lower_bound=Config.getInt("lower_bound", "rain_rate"),
                        upper_bound=Config.getInt("warning", "rain_rate"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                        lower_bound=Config.getInt("warning", "rain_rate"),
                        upper_bound=Config.getInt("error", "rain_rate"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_DANGER,
                        lower_bound=Config.getInt("error", "rain_rate"),
                        upper_bound=Config.getInt("upper_bound", "rain_rate"),
                    ),
                ),
            ),
            barometer=Chart(
                value=self.weather.barometer[0],
                title="Barometro",
                min=Config.getInt("lower_bound", "barometer"),
                max=Config.getInt("upper_bound", "barometer"),
                unit_of_measurement=self.weather.barometer[1],
                thresholds=(
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_NORMAL,
                        upper_bound=Config.getInt("upper_bound", "barometer"),
                        lower_bound=Config.getInt("warning", "barometer"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                        upper_bound=Config.getInt("warning", "barometer"),
                        lower_bound=Config.getInt("error", "barometer"),
                    ),
                    Threshold(
                        threshold_type=ThresholdType.THRESHOLD_TYPE_DANGER,
                        upper_bound=Config.getInt("error", "barometer"),
                        lower_bound=Config.getInt("lower_bound", "barometer"),
                    ),
                ),
            ),
            updated_at=int(self.weather.updated_at.timestamp())
        )

        return response
