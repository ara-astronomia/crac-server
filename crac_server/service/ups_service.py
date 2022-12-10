import logging
from datetime import datetime
from crac_protobuf.chart_pb2 import (
    ChartStatus,  # type: ignore
)
from crac_protobuf.ups_pb2_grpc import UpsServicer
from crac_protobuf.ups_pb2 import (
    UpsRequest,  # type: ignore
    UpsResponse,  # type: ignore
    UpsStatus,  # type: ignore
)
from crac_server.component.ups import UPS
from crac_server.config import Config
from crac_server.converter.chart_builder import build_chart
from typing import Union


logger = logging.getLogger(__name__)


class UpsService(UpsServicer):

    def __init__(self) -> None:
        super().__init__()
        
    def GetStatus(self, request: UpsRequest, context) -> UpsResponse:
        response = UpsResponse(
            updated_at=int(datetime.now().timestamp()),
            interval=UPS.time_expired
        )
        for device in Config.getValue("ups_list", "ups").split(","):
            ups = UPS.status_for(device)
            response.devices.append(device)
            response.charts.append(
                build_chart(
                    value=float(ups['battery.charge']),
                    title="Batteria",
                    urn=f"ups.{device}.chart.battery",
                    min=0,
                    max=100,
                    unit_of_measurement="%",
                    range_normal=({
                        "upper_bound": Config.getFloat("upper_bound", "battery_ok"),
                        "lower_bound": Config.getFloat("lower_bound", "battery_ok"),
                    },),
                    range_warn=({
                        "upper_bound": Config.getFloat("upper_bound", "battery_warning"),
                        "lower_bound": Config.getFloat("lower_bound", "battery_warning"),
                    },),
                    range_danger=({
                        "upper_bound": Config.getFloat("upper_bound", "battery_danger"),
                        "lower_bound": Config.getFloat("lower_bound", "battery_danger"),
                    },)
                )
            )
            response.charts.append(
                build_chart(
                    value=float(ups['output.voltage']),
                    title="Batteria",
                    urn=f"ups.{device}.chart.voltage",
                    min=Config.getFloat("lower_bound", "voltage_danger_lower"),
                    max=Config.getFloat("upper_bound", "voltage_danger_upper"),
                    unit_of_measurement="V",
                    range_normal=({
                        "upper_bound": Config.getFloat("upper_bound", "voltage_ok"),
                        "lower_bound": Config.getFloat("lower_bound", "voltage_ok"),
                    },),
                    range_danger=({
                        "upper_bound": Config.getFloat("upper_bound", "voltage_danger_upper"),
                        "lower_bound": Config.getFloat("lower_bound", "voltage_danger_upper"),
                    }, {
                        "upper_bound": Config.getFloat("upper_bound", "voltage_danger_lower"),
                        "lower_bound": Config.getFloat("lower_bound", "voltage_danger_lower"),
                    },)
                )
            )
        response.status = self.calculate_status(UPS, response.charts)
        logger.info(f"ups response is {response}")
        return response

    def timestamp_or_none(self, updated_at: Union[datetime, None]) -> int:
        if updated_at != None:
            return int(updated_at.timestamp()) 
        else: 
            return 0

    def calculate_status(self, ups, charts):
        status = UpsStatus.UPS_STATUS_UNSPECIFIED
        #if not ups.is_unavailable:
        for chart in charts:
            logger.debug("chart is:")
            logger.debug(chart)
            if status < UpsStatus.UPS_STATUS_NORMAL and chart.status == ChartStatus.CHART_STATUS_NORMAL:
                status = UpsStatus.UPS_STATUS_NORMAL
            if status < UpsStatus.UPS_STATUS_WARNING and chart.status == ChartStatus.CHART_STATUS_WARNING:
                status = UpsStatus.UPS_STATUS_WARNING
            if status < UpsStatus.UPS_STATUS_DANGER and chart.status == ChartStatus.CHART_STATUS_DANGER:
                status = UpsStatus.UPS_STATUS_DANGER
            logger.info(f"now ups status is: {status}")
        
        return status