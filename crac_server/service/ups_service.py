import logging
from datetime import datetime
from crac_protobuf.chart_pb2 import (
    ChartStatus,
)
from crac_protobuf.ups_pb2_grpc import UpsServicer
from crac_protobuf.ups_pb2 import (
    UpsRequest,
    UpsResponse,
    UpsStatus,
    UpsChart,
)
from crac_server.component.ups import UPS
from crac_server.config import Config
from crac_server.converter.chart_builder import build_chart
from typing import Union


logger = logging.getLogger(__name__)


class UpsService(UpsServicer):

    def __init__(self) -> None:
        super().__init__()

    def _chart_specs(self):
        return (
            ("battery_charge", "battery", "Batteria", "%", dict(
                min=0,
                max=100,
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
                },),
            )),
            ("input_voltage", "voltage", "Batteria", "V", dict(
                min=Config.getFloat("lower_bound", "voltage_danger_lower"),
                max=Config.getFloat("upper_bound", "voltage_danger_upper"),
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
                },),
            )),
            ("output_current", "current", "Corrente", "A", dict(
                min=Config.getFloat("lower_bound", "ampere_ok"),
                max=Config.getFloat("upper_bound", "ampere_danger"),
                range_normal=({
                    "upper_bound": Config.getFloat("upper_bound", "ampere_ok"),
                    "lower_bound": Config.getFloat("lower_bound", "ampere_ok"),
                },),
                range_danger=({
                    "upper_bound": Config.getFloat("upper_bound", "ampere_danger"),
                    "lower_bound": Config.getFloat("lower_bound", "ampere_danger"),
                },),
            )),
        )

    def GetStatus(self, request: UpsRequest, context) -> UpsResponse:
        response = UpsResponse(
            updated_at=self.timestamp_or_none(datetime.now()),
            interval=UPS.time_expired
        )
        for device in Config.getValue("ups_list", "ups").split(","):
            try:
                ups = UPS.status_for(device)
            except Exception as e:
                logger.error(f"Impossibile leggere l'UPS {device}: {e}")
                continue
            response.devices.append(device)
            for key, urn_suffix, title, unit, chart_kwargs in self._chart_specs():
                if ups.get(key) is None:
                    continue
                response.charts.append(
                    UpsChart(
                        chart = build_chart(
                            value=float(ups[key]),
                            title=title,
                            urn=f"ups.{device}.chart.{urn_suffix}",
                            unit_of_measurement=unit,
                            **chart_kwargs
                        )
                    )
                )
        response.status = self.calculate_status(UPS, response.charts)
        logger.debug(f"ups response is {response}")
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
            if status < UpsStatus.UPS_STATUS_NORMAL and chart.chart.status == ChartStatus.CHART_STATUS_NORMAL:
                status = UpsStatus.UPS_STATUS_NORMAL
            if status < UpsStatus.UPS_STATUS_WARNING and chart.chart.status == ChartStatus.CHART_STATUS_WARNING:
                status = UpsStatus.UPS_STATUS_WARNING
            if status < UpsStatus.UPS_STATUS_DANGER and chart.chart.status == ChartStatus.CHART_STATUS_DANGER:
                status = UpsStatus.UPS_STATUS_DANGER
            logger.debug(f"now ups status is: {status}")
        
        return status
