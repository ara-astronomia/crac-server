from crac_protobuf.chart_pb2_grpc import WeatherServicer
from crac_protobuf.chart_pb2 import (
    WeatherRequest,  # type: ignore
    WeatherResponse,  # type: ignore
)
from crac_server.component.weather import WEATHER
from crac_server.converter.weather_converter import WeatherConverter


class WeatherService(WeatherServicer):

    def GetStatus(self, request: WeatherRequest, context) -> WeatherResponse:
        weather_handler = WeatherConverter()
        return weather_handler.convert(WEATHER)

