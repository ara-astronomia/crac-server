from abc import ABC, abstractmethod


class Ups(ABC):
    def __init__(self) -> None:
        self.time_expired = 660

    @abstractmethod
    def status_for(self, device: str) -> dict[str,str]:
        pass