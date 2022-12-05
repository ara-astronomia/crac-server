from abc import ABC, abstractmethod


class Ups(ABC):

    @abstractmethod
    def status_for(self, device: str) -> dict:
        pass