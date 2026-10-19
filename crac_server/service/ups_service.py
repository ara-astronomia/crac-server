import asyncio
import logging
import math
from datetime import datetime
from crac_protobuf.chart_pb2 import (
    ChartStatus,
)
from crac_protobuf.emergency_closure_pb2 import (
    EmergencyClosureTrigger,  # type: ignore
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
from crac_server.service.ups_emergency import critical_thresholds, enabled_checks, ups_emergency
from crac_server.status_log import ErrorCause, StatusLogger
from typing import Union


logger = logging.getLogger(__name__)


BATTERY_STATUS_BY_FLAG = {
    "OL": BatteryStatus.BATTERY_STATUS_ONLINE,
    "OB": BatteryStatus.BATTERY_STATUS_ONBATTERY,
    "LB": BatteryStatus.BATTERY_STATUS_LOWBATTERY,
    "DISCHRG": BatteryStatus.BATTERY_STATUS_DISCHARGE,
}
FLAGS_WITHOUT_A_STATUS_VALUE = frozenset(("RB", "FSD", "ALARM"))
MIN_CHECK_INTERVAL = 30
UPS = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_UPS


class UpsService(UpsServicer):

    def __init__(self) -> None:
        super().__init__()
        self._validate_metrics()
        self._validate_emergency()
        self.check_interval = self._check_interval()
        self._watch_log = StatusLogger(logger, "UPS watch")

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

    def _validate_emergency(self):
        """The emergency configuration is validated here so that a broken
        one stops the startup, and read again on every check."""
        checks = enabled_checks()
        metrics = Config.get_section("ups_metrics")
        unread = sorted(checks - set(metrics))
        if unread:
            raise RuntimeError(
                f"[ups_emergency]: checks that the server does not read: {unread}. "
                f"Add them to [ups_metrics] or remove them from enabled_checks."
            )
        critical_thresholds()
        Config.getRequiredBoolean("block_on_unspecified", "ups_emergency")

    @staticmethod
    def _check_interval() -> float:
        """A shorter interval would only spin the loop: the UPS drivers
        refresh their readings far less often. NaN and infinity would
        silently stop the checks."""
        interval = Config.getRequiredFloat("check_interval", "ups")
        if not MIN_CHECK_INTERVAL <= interval < math.inf:
            raise ValueError(
                f"ups.check_interval must be a number of seconds, at least {MIN_CHECK_INTERVAL}: {interval}"
            )
        return interval

    def _charts_by_key(self, device: str, ups: dict) -> dict:
        charts = {}
        for key, urn_suffix, title, unit in self._chart_specs():
            if ups.get(key) is None:
                continue
            battery_statuses = self._battery_statuses(device, ups.get("ups_status")) if key == "battery_charge" else []
            charts[key] = UpsChart(
                chart=build_chart_from_config(
                    key,
                    value=float(ups[key]),
                    title=title,
                    urn=f"ups.{device}.chart.{urn_suffix}",
                    unit_of_measurement=unit,
                ),
                battery_statuses=battery_statuses,
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
        """A display read, run by gRPC in a thread without an event loop:
        the emergency reaction lives in watch(), on the loop."""
        return self._respond({device: self._read_or_error(device) for device in self._configured_devices()})[0]

    async def check(self) -> UpsResponse:
        """Read every UPS and report to the emergency closure: a single
        device in a critical condition is enough, and one that could not
        be read or cannot be judged neither starts nor settles a closure."""
        readings = {}
        for device in self._configured_devices():
            readings[device] = await asyncio.to_thread(self._read_or_error, device)
        response, readable = self._respond(readings)
        critical = False
        for device, (reading, charts_by_key) in readable.items():
            if ups_emergency().device_is_critical(device, reading, charts_by_key):
                critical = True
        unreadable = [device for device in readings if device not in readable]
        for device in unreadable:
            ups_emergency().device_lost(device)
        self._report(critical, unreadable)
        return response

    async def watch(self):
        """Check every UPS every check_interval seconds, so that the closure
        does not wait for a client to ask. A failed check is logged, once
        per kind of failure, and the next one runs anyway."""
        logger.info("UPS watch: checking every %s seconds", self.check_interval)
        while True:
            try:
                await self.check()
                self._watch_log.record("running")
            except Exception as e:
                self._watch_log.record(
                    f"check failed: {type(e).__name__}", ErrorCause.UNEXPECTED_FAILURE, detail=str(e), exc_info=e,
                )
            await asyncio.sleep(self.check_interval)

    @staticmethod
    def _read_or_error(device: str):
        """The reading or the error it ended with, so that the response
        builder can treat both without knowing where they came from."""
        try:
            return ups().status_for(device)
        except Exception as e:
            return e

    def _report(self, critical: bool, unreadable) -> None:
        if unreadable:
            self._watch_log.record(f"cannot check {unreadable}", ErrorCause.DEVICE_UNREACHABLE)
            if not critical:
                return
        emergency_closure().report(UPS, critical)

    def _respond(self, readings: dict) -> tuple:
        """Build the response, isolating a device that could not be read
        or cannot be judged: neither can say it is fine. Returns the
        response and the devices that could be read, with reading and charts."""
        response = UpsResponse(
            updated_at=self.timestamp_or_none(datetime.now()),
            interval=ups().time_expired
        )
        readable = {}
        unreadable = []
        for device, reading in readings.items():
            try:
                if isinstance(reading, Exception):
                    raise reading
                charts_by_key = self._charts_by_key(device, reading)
            except ChartConfigError:
                raise
            except Exception as e:
                logger.error(f"Impossibile leggere l'UPS {device}: {e}")
                unreadable.append(device)
                response.device_states.append(
                    UpsDevice(name=device, status=UpsStatus.UPS_STATUS_UNSPECIFIED)
                )
                continue
            if not ups_emergency().can_be_judged(device, reading, charts_by_key):
                logger.error(f"The UPS {device} does not report an enabled check: it cannot be judged")
                unreadable.append(device)
                response.device_states.append(
                    UpsDevice(name=device, status=UpsStatus.UPS_STATUS_UNSPECIFIED)
                )
                continue
            charts = list(charts_by_key.values())
            readable[device] = (reading, charts_by_key)
            response.devices.append(device)
            response.charts.extend(charts)
            response.device_states.append(
                UpsDevice(name=device, status=self.calculate_status(charts))
            )
        response.status = self._overall_status(response.charts, unreadable)
        response.emergency_closure.CopyFrom(emergency_closure().state())
        return response, readable

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
