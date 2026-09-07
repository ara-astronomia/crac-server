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


class UpsService(UpsServicer):

    def __init__(self) -> None:
        super().__init__()
        self._validate_metrics()

    def _validate_metrics(self):
        """
        Validate the configuration at startup. A broken one found while polling
        would discard every device on every call, blaming the UPS for a mistake
        of ours.
        """
        self._configured_devices()
        try:
            enabled = Config.get_section("ups_metrics")
        except KeyError:
            raise RuntimeError(
                "[ups_metrics] mancante in config.ini: e' la sezione che elenca "
                "le metriche da leggere, nella forma 'nome_nostro = nome_NUT'"
            )
        self._reject_metrics_left_without_a_value(enabled)
        self._reject_metrics_that_produce_no_chart(enabled)
        self._read_thresholds_of(enabled)

    def _configured_devices(self):
        """
        Names are written by hand: a stray space would build an urn no client
        can match, and an empty entry a device that can never be read, pinning
        the overall status to UNSPECIFIED forever.
        """
        devices = [name.strip() for name in Config.getValue("ups_list", "ups").split(",")]
        if not any(devices):
            raise RuntimeError("ups_list e' vuota: nessun UPS da sorvegliare")
        if not all(devices):
            raise RuntimeError(f"ups_list contiene nomi vuoti, controllare le virgole: {Config.getValue('ups_list', 'ups')!r}")
        duplicated = {name for name in devices if devices.count(name) > 1}
        if duplicated:
            raise RuntimeError(f"ups_list contiene device ripetuti: {sorted(duplicated)}")
        return devices

    def _reject_metrics_left_without_a_value(self, enabled):
        """An emptied key is dropped by get_section, silently unmonitoring it."""
        empty = [key for key in Config.get_section_keys("ups_metrics") if key not in enabled]
        if empty:
            raise RuntimeError(f"[ups_metrics]: metriche senza valore, rimuoverle o valorizzarle: {sorted(empty)}")

    def _reject_metrics_that_produce_no_chart(self, enabled):
        """
        Such a metric shows nothing, yet the device is still discarded when it
        is missing: all of the risk, none of the benefit.
        """
        chartable = {key for key, _, _, _, _ in self._chart_specs()}
        unknown = set(enabled) - chartable
        if unknown:
            raise RuntimeError(f"[ups_metrics]: metriche che non producono alcun grafico: {sorted(unknown)}")

    def _read_thresholds_of(self, enabled):
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
        for device in self._configured_devices():
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
                UpsDevice(name=device, status=self.calculate_status(charts))
            )
        response.status = self._overall_status(response.charts, unreadable)
        logger.debug(f"ups response is {response}")
        return response

    def _overall_status(self, charts, unreadable):
        """
        Nothing is known about a UPS that does not answer, so reporting NORMAL
        because the others are fine would be a false reassurance. A danger
        already detected elsewhere is never downgraded.
        """
        status = self.calculate_status(charts)
        if unreadable and status != UpsStatus.UPS_STATUS_DANGER:
            logger.warning(f"UPS non leggibili {unreadable}: stato riportato come UNSPECIFIED")
            return UpsStatus.UPS_STATUS_UNSPECIFIED
        return status

    def timestamp_or_none(self, updated_at: Union[datetime, None]) -> int:
        if updated_at != None:
            return int(updated_at.timestamp()) 
        else: 
            return 0

    def calculate_status(self, charts):
        status = UpsStatus.UPS_STATUS_UNSPECIFIED
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
