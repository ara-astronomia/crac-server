from abc import ABC, abstractmethod
from crac_server.config import Config


METRICS = ("battery_charge", "input_voltage", "output_current")


class Ups(ABC):
    def __init__(self, host: str, login: str, password: str, time_expired: int) -> None:
        self.time_expired = time_expired

    def status_for(self, device: str) -> dict[str, str]:
        disabled_metrics = Config.getValue("disabled_metrics", "ups").split(",")
        raw = self._read(device)
        result = {"ups_status": raw.get("ups_status")}
        for key in METRICS:
            if key in disabled_metrics:
                continue
            if raw.get(key) is None:
                raise RuntimeError(f"UPS {device}: metrica '{key}' non disponibile e non esclusa da disabled_metrics")
            result[key] = raw[key]
        return result

    @abstractmethod
    def _read(self, device: str) -> dict[str, str]:
        pass
