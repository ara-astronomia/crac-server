from crac_protobuf.chart_pb2_grpc import WeatherServicer
from crac_protobuf.chart_pb2 import (
    WeatherRequest,
    WeatherResponse,
)
from crac_server.handler.weather_handler import WeatherHandler


class WeatherService(WeatherServicer):

    def GetStatus(self, request: WeatherRequest, context) -> WeatherResponse:
        weather_handler = WeatherHandler()
        return weather_handler.handle(request)

