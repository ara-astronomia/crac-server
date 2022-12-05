from crac_protobuf.ups_pb2_grpc import UpsServicer
from crac_protobuf.ups_pb2 import (
    UpsRequest,  # type: ignore
    UpsResponse,  # type: ignore
    UpsStatus,  # type: ignore
)
from crac_protobuf.chart_pb2 import (
    Chart, # type: ignore
    Threshold, # type: ignore
    ThresholdType, # type: ignore
    ChartStatus,  # type: ignore
)
from crac_server.component.ups import UPS
from crac_server.config import Config


class WeatherService(UpsServicer):

    def __init__(self) -> None:
        super().__init__()
        
    def GetStatus(self, request: UpsRequest, context) -> UpsResponse:
        for device in Config.getValue("ups", "ups_list").split(","):
            ups = UPS.status_for(device)

            chart = Chart(

            )