from abc import ABC, abstractmethod


class Ups(ABC):
    def __init__(self, time_expired: int) -> None:
        self.time_expired = time_expired

    @abstractmethod
    def status_for(self, device: str) -> dict[str,str]:
        pass