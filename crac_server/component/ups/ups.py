from abc import ABC, abstractmethod
from crac_server.config import Config


class Ups(ABC):
    def __init__(self, host: str, port: int, login: str, password: str, time_expired: int) -> None:
        self.time_expired = time_expired

    def status_for(self, device: str) -> dict[str, str]:
        metrics = Config.get_section("ups_metrics")
        raw = self._read(device)
        result = {}
        for our_name, source_name in metrics.items():
            if raw.get(source_name) is None:
                raise RuntimeError(
                    f"UPS {device}: metrica '{our_name}' ({source_name}) non disponibile. "
                    f"Se questo UPS non la espone, toglierla da [ups_metrics] in config.ini: "
                    f"finche' resta elencata il device viene scartato per intero, "
                    f"comprese le metriche leggibili."
                )
            result[our_name] = raw[source_name]
        return result

    @abstractmethod
    def _read(self, device: str) -> dict[str, str]:
        pass
