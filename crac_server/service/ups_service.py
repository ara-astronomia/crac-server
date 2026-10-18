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
    BatteryStatus,
)
from crac_server.component.ups import ups
from crac_server.config import Config
from crac_server.converter.chart_config import ChartConfigError, build_chart_from_config
from crac_server.service.emergency_closure import emergency_closure
from typing import Union


logger = logging.getLogger(__name__)


BATTERY_STATUS_BY_FLAG = {
    "OL": BatteryStatus.BATTERY_STATUS_ONLINE,
    "OB": BatteryStatus.BATTERY_STATUS_ONBATTERY,
    "LB": BatteryStatus.BATTERY_STATUS_LOWBATTERY,
    "DISCHRG": BatteryStatus.BATTERY_STATUS_DISCHARGE,
}
FLAGS_WITHOUT_A_STATUS_VALUE = frozenset(("RB", "FSD", "ALARM"))


class UpsService(UpsServicer):

    def __init__(self) -> None:
        super().__init__()
        self._validate_metrics()

    def _validate_metrics(self):
        """Validate the configuration at startup: a broken one found while
        polling would discard every device on every call, blaming the UPS
        for a mistake of ours."""
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
        self._reject_unusable_thresholds_of(enabled)

    def _configured_devices(self):
        """Names are written by hand: a stray space would build an urn no
        client can match, and an empty entry a device that can never be
        read, pinning the overall status to UNSPECIFIED forever."""
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
        """Such a metric shows nothing, yet the device is still discarded
        when it is missing: all of the risk, none of the benefit."""
        chartable = {key for key, _, _, _ in self._chart_specs()}
        consumed = self._consumed_without_a_chart(enabled)
        unknown = set(enabled) - chartable - consumed
        if unknown:
            raise RuntimeError(f"[ups_metrics]: metriche che non producono alcun grafico: {sorted(unknown)}")

    def _consumed_without_a_chart(self, enabled):
        """ups_status feeds the battery statuses, which ride on the battery
        chart: without it there is no place for the flags."""
        if "ups_status" not in enabled:
            return set()
        if "battery_charge" not in enabled:
            raise RuntimeError(
                "[ups_metrics]: ups_status richiede battery_charge: "
                "i suoi valori viaggiano sul grafico della batteria"
            )
        return {"ups_status"}

    def _reject_unusable_thresholds_of(self, enabled):
        """Reading the thresholds catches the missing ones, building a chart
        out of them also catches the bands no reading can ever fall into:
        both stop the startup rather than surface at the first poll."""
        for key, urn_suffix, title, unit in self._chart_specs():
            if key in enabled:
                build_chart_from_config(
                    key,
                    value=0,
                    title=title,
                    urn=f"ups.chart.{urn_suffix}",
                    unit_of_measurement=unit,
                )

    def _chart_specs(self):
        return (
            ("battery_charge", "battery", "Batteria", "%"),
            ("input_voltage", "voltage", "Tensione", "V"),
            ("output_current", "current", "Corrente", "A"),
        )

    def _build_charts(self, device: str, ups: dict) -> list:
        charts = []
        for key, urn_suffix, title, unit in self._chart_specs():
            if ups.get(key) is None:
                continue
            battery_statuses = self._battery_statuses(device, ups.get("ups_status")) if key == "battery_charge" else []
            charts.append(
                UpsChart(
                    chart=build_chart_from_config(
                        key,
                        value=float(ups[key]),
                        title=title,
                        urn=f"ups.{device}.chart.{urn_suffix}",
                        unit_of_measurement=unit,
                    ),
                    battery_statuses=battery_statuses,
                )
            )
        return charts

    def _battery_statuses(self, device: str, raw: Union[str, None]) -> list:
        if raw is None:
            return []
        statuses = []
        for flag in raw.split():
            if flag in BATTERY_STATUS_BY_FLAG:
                statuses.append(BATTERY_STATUS_BY_FLAG[flag])
            elif flag in FLAGS_WITHOUT_A_STATUS_VALUE:
                logger.warning(f"UPS {device}: il flag NUT '{flag}' non ha un valore in BatteryStatus")
            else:
                logger.debug(f"UPS {device}: flag NUT informativo '{flag}' ignorato")
        return statuses

    def GetStatus(self, request: UpsRequest, context) -> UpsResponse:
        response = UpsResponse(
            updated_at=self.timestamp_or_none(datetime.now()),
            interval=ups().time_expired
        )
        unreadable = []
        for device in self._configured_devices():
            try:
                reading = ups().status_for(device)
                charts = self._build_charts(device, reading)
            except ChartConfigError:
                raise
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
        response.emergency_closure.CopyFrom(emergency_closure().state())
        logger.debug(f"ups response is {response}")
        return response

    def _overall_status(self, charts, unreadable):
        """Nothing is known about a UPS that does not answer, so reporting
        NORMAL because the others are fine would be a false reassurance. A
        danger already detected elsewhere is never downgraded."""
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
            if not chart.chart.thresholds:
                continue
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
