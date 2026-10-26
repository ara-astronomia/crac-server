from abc import ABC, abstractmethod
from crac_server.config import Config


class Ups(ABC):
    def __init__(self, host: str, port: int, login: str, password: str, time_expired: int) -> None:
        self.time_expired = time_expired

    def status_for(self, device: str) -> dict[str, str]:
        """What the device reports of the metrics we read: what does not
        arrive is simply missing, and what is missing is judged by the
        safety checks of the emergency layer, not discarded here."""
        raw = self._read(device)
        metrics = Config.get_section("ups_metrics")
        result = {}
        for our_name, source_name in metrics.items():
            if raw.get(source_name) is not None:
                result[our_name] = raw[source_name]
        return result

    @abstractmethod
    def _read(self, device: str) -> dict[str, str]:
        pass
