from abc import ABC, abstractmethod
from crac_server.config import Config


METRICS = (
    ("battery_charge", "battery.charge"),
    ("input_voltage", "input.voltage"),
    ("output_current", "output.current"),
    ("ups_status", "ups.status"),
)


class Ups(ABC):
    def __init__(self, host: str, login: str, password: str, time_expired: int) -> None:
        self.time_expired = time_expired

    def status_for(self, device: str) -> dict[str, str]:
        enabled_metrics = [m for m in Config.getValue("enabled_metrics", "ups").split(",") if m]
        unknown = set(enabled_metrics) - {key for key, _ in METRICS}
        if unknown:
            raise RuntimeError(f"enabled_metrics contiene metriche sconosciute: {sorted(unknown)}")
        raw = self._read(device)
        result = {}
        for key in enabled_metrics:
            if raw.get(key) is None:
                raise RuntimeError(f"UPS {device}: metrica '{key}' non disponibile (elencata in enabled_metrics)")
            result[key] = raw[key]
        return result

    @abstractmethod
    def _read(self, device: str) -> dict[str, str]:
        pass
