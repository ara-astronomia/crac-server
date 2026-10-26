import logging
from functools import lru_cache
from time import monotonic
from typing import NamedTuple

from crac_protobuf.chart_pb2 import ChartStatus  # type: ignore
from crac_protobuf.ups_pb2 import BatteryStatus  # type: ignore

from crac_server.config import Config


logger = logging.getLogger(__name__)

EMERGENCY_CHECKS = ("battery_charge", "ups_status", "output_current")


class UpsCriticality(NamedTuple):
    critical_time: float
    critical_battery_percentage: float


def critical_thresholds() -> UpsCriticality:
    """The global thresholds of this installation: a per device override
    would go through here, without touching the checks below."""
    return UpsCriticality(
        critical_time=Config.getRequiredFloat("critical_time", "ups_emergency"),
        critical_battery_percentage=Config.getRequiredFloat("critical_battery_percentage", "ups_emergency"),
    )


def enabled_checks() -> frozenset:
    """The checks that can start the emergency closure: a check that is not
    listed is never evaluated. Unknown or empty means the configuration
    cannot protect the observatory."""
    names = [name.strip() for name in Config.getValue("enabled_checks", "ups_emergency").split(",")]
    if not any(names):
        raise RuntimeError("[ups_emergency]: enabled_checks is empty: no check can protect the observatory")
    unknown = [name for name in names if name not in EMERGENCY_CHECKS]
    if unknown:
        raise RuntimeError(f"[ups_emergency]: unknown checks {unknown}, the valid ones are {list(EMERGENCY_CHECKS)}")
    return frozenset(names)


class UnevaluableDevice(RuntimeError):
    """A device that does not report the data of an enabled check cannot
    say that it is fine: it counts like a device that does not answer."""


class UpsEmergency:
    """Tells when a UPS device is critical: a battery at or below the
    critical percentage at once, a device on battery or with a dangerous
    output current only after critical_time continuous seconds."""

    def __init__(self) -> None:
        self._sustained_since = {}

    def device_is_critical(self, device: str, reading: dict, charts_by_key: dict) -> bool:
        checks = enabled_checks()
        self._ensure_evaluable(checks, device, reading, charts_by_key)
        if self._battery_is_critical(checks, reading):
            return True
        return self._sustained_is_critical(checks, device, reading, charts_by_key)

    def can_be_judged(self, device: str, reading: dict, charts_by_key: dict) -> bool:
        """Whether the device reports the data of every enabled check: one
        that cannot be judged counts like one that does not answer."""
        try:
            self._ensure_evaluable(enabled_checks(), device, reading, charts_by_key)
        except UnevaluableDevice:
            return False
        return True

    def device_lost(self, device: str) -> None:
        """An unreadable device cannot confirm its condition: the sustained
        count starts over when it comes back."""
        self._sustained_since.pop(device, None)

    @staticmethod
    def _ensure_evaluable(checks, device: str, reading: dict, charts_by_key: dict) -> None:
        """The data that the enabled checks read, without which nobody can
        say the device is fine."""
        if "battery_charge" in checks and reading.get("battery_charge") is None:
            raise UnevaluableDevice(f"UPS {device}: battery_charge is an enabled check but the device did not report it")
        if "ups_status" in checks:
            if reading.get("ups_status") is None:
                raise UnevaluableDevice(f"UPS {device}: ups_status is an enabled check but the device did not report it")
            if charts_by_key.get("battery_charge") is None:
                raise UnevaluableDevice(f"UPS {device}: ups_status is an enabled check but the battery chart is missing")
        if "output_current" in checks and charts_by_key.get("output_current") is None:
            raise UnevaluableDevice(f"UPS {device}: output_current is an enabled check but the current chart is missing")

    @staticmethod
    def _battery_is_critical(checks, reading: dict) -> bool:
        if "battery_charge" not in checks:
            return False
        return float(reading["battery_charge"]) <= critical_thresholds().critical_battery_percentage

    def _sustained_is_critical(self, checks, device: str, reading: dict, charts_by_key: dict) -> bool:
        if not self._sustained_condition(checks, charts_by_key):
            self._sustained_since.pop(device, None)
            return False
        started = self._sustained_since.setdefault(device, monotonic())
        return monotonic() - started >= critical_thresholds().critical_time

    def _sustained_condition(self, checks, charts_by_key: dict) -> bool:
        return (
            "ups_status" in checks and self._on_battery(charts_by_key)
            or "output_current" in checks and self._current_is_dangerous(charts_by_key)
        )

    @staticmethod
    def _on_battery(charts_by_key: dict) -> bool:
        return BatteryStatus.BATTERY_STATUS_ONBATTERY in charts_by_key["battery_charge"].battery_statuses

    @staticmethod
    def _current_is_dangerous(charts_by_key: dict) -> bool:
        return charts_by_key["output_current"].chart.status == ChartStatus.CHART_STATUS_DANGER


@lru_cache(maxsize=1)
def ups_emergency() -> UpsEmergency:
    return UpsEmergency()
