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
    UpsDevice,
)
from crac_server.component.ups import UPS
from crac_server.config import Config
from crac_server.converter.chart_builder import build_chart
from typing import Union


logger = logging.getLogger(__name__)

# Metriche lette di proposito senza produrre un grafico: ups_status serve alla
# chiusura automatica (#22) e come battery_statuses del protocollo (#81).
METRICS_WITHOUT_CHART = {"ups_status"}


class UpsService(UpsServicer):

    def __init__(self) -> None:
        super().__init__()
        self._validate_metrics()

    def _validate_metrics(self):
        """
        [ups_metrics] e le soglie vanno verificate all'avvio: una config rotta
        scoperta durante il polling scarta ogni device ad ogni chiamata, con un
        messaggio che incolpa l'UPS invece della configurazione.
        """
        enabled = Config.get_section("ups_metrics")

        # Una chiave svuotata per sbaglio verrebbe scartata da get_section
        # senza un errore, e quella metrica smetterebbe di essere letta.
        empty = [key for key in Config.get_section_keys("ups_metrics") if key not in enabled]
        if empty:
            raise RuntimeError(f"[ups_metrics]: metriche senza valore, rimuoverle o valorizzarle: {sorted(empty)}")

        # Una metrica che il service non sa graficare non produce nulla, ma
        # resta obbligatoria sul device: tutto il rischio, nessun beneficio.
        chartable = {key for key, _, _, _, _ in self._chart_specs()}
        unknown = set(enabled) - chartable - METRICS_WITHOUT_CHART
        if unknown:
            raise RuntimeError(f"[ups_metrics]: metriche che non producono alcun grafico: {sorted(unknown)}")

        for key, _, _, _, chart_kwargs_fn in self._chart_specs():
            if key in enabled:
                chart_kwargs_fn()

    def _chart_specs(self):
        return (
            ("battery_charge", "battery", "Batteria", "%", lambda: dict(
                min=0,
                max=100,
                range_normal=({
                    "upper_bound": Config.getRequiredFloat("upper_bound", "battery_charge.ok"),
                    "lower_bound": Config.getRequiredFloat("lower_bound", "battery_charge.ok"),
                },),
                range_warn=({
                    "upper_bound": Config.getRequiredFloat("upper_bound", "battery_charge.warning"),
                    "lower_bound": Config.getRequiredFloat("lower_bound", "battery_charge.warning"),
                },),
                range_danger=({
                    "upper_bound": Config.getRequiredFloat("upper_bound", "battery_charge.danger"),
                    "lower_bound": Config.getRequiredFloat("lower_bound", "battery_charge.danger"),
                },),
            )),
            ("input_voltage", "voltage", "Batteria", "V", lambda: dict(
                min=Config.getRequiredFloat("lower_bound", "input_voltage.danger_lower"),
                max=Config.getRequiredFloat("upper_bound", "input_voltage.danger_upper"),
                range_normal=({
                    "upper_bound": Config.getRequiredFloat("upper_bound", "input_voltage.ok"),
                    "lower_bound": Config.getRequiredFloat("lower_bound", "input_voltage.ok"),
                },),
                range_danger=({
                    "upper_bound": Config.getRequiredFloat("upper_bound", "input_voltage.danger_upper"),
                    "lower_bound": Config.getRequiredFloat("lower_bound", "input_voltage.danger_upper"),
                }, {
                    "upper_bound": Config.getRequiredFloat("upper_bound", "input_voltage.danger_lower"),
                    "lower_bound": Config.getRequiredFloat("lower_bound", "input_voltage.danger_lower"),
                },),
            )),
            ("output_current", "current", "Corrente", "A", lambda: dict(
                min=Config.getRequiredFloat("lower_bound", "output_current.ok"),
                max=Config.getRequiredFloat("upper_bound", "output_current.danger"),
                range_normal=({
                    "upper_bound": Config.getRequiredFloat("upper_bound", "output_current.ok"),
                    "lower_bound": Config.getRequiredFloat("lower_bound", "output_current.ok"),
                },),
                range_danger=({
                    "upper_bound": Config.getRequiredFloat("upper_bound", "output_current.danger"),
                    "lower_bound": Config.getRequiredFloat("lower_bound", "output_current.danger"),
                },),
            )),
        )

    def _build_charts(self, device: str, ups: dict) -> list:
        charts = []
        for key, urn_suffix, title, unit, chart_kwargs_fn in self._chart_specs():
            if ups.get(key) is None:
                continue
            charts.append(
                UpsChart(
                    chart = build_chart(
                        value=float(ups[key]),
                        title=title,
                        urn=f"ups.{device}.chart.{urn_suffix}",
                        unit_of_measurement=unit,
                        **chart_kwargs_fn()
                    )
                )
            )
        return charts

    def GetStatus(self, request: UpsRequest, context) -> UpsResponse:
        response = UpsResponse(
            updated_at=self.timestamp_or_none(datetime.now()),
            interval=UPS.time_expired
        )
        unreadable = []
        for device in Config.getValue("ups_list", "ups").split(","):
            try:
                ups = UPS.status_for(device)
                charts = self._build_charts(device, ups)
            except Exception as e:
                logger.error(f"Impossibile leggere l'UPS {device}: {e}")
                unreadable.append(device)
                response.device_states.append(
                    UpsDevice(name=device, status=UpsStatus.UPS_STATUS_UNSPECIFIED)
                )
                continue
            response.devices.append(device)
            response.charts.extend(charts)
            response.device_states.append(
                UpsDevice(name=device, status=self.calculate_status(UPS, charts))
            )
        response.status = self.calculate_status(UPS, response.charts)
        if unreadable and response.status != UpsStatus.UPS_STATUS_DANGER:
            # su un UPS che non risponde non sappiamo nulla: riportare NORMAL
            # perche' gli altri stanno bene sarebbe una rassicurazione falsa.
            # Un pericolo gia' rilevato altrove non viene pero' declassato.
            logger.warning(f"UPS non leggibili {unreadable}: stato riportato come UNSPECIFIED")
            response.status = UpsStatus.UPS_STATUS_UNSPECIFIED
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
