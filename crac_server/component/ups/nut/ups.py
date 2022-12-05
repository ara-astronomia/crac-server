from crac_server.component.ups.ups import Ups as UpsBase
from nut2 import PyNUTClient

class Ups(UpsBase):
    def __init__(self, host: str) -> None:
        self.client = PyNUTClient(host)

    def status_for(self, device: str):
        return self.client.list_vars(device)

    def list_ups(self):
        return self.client.list_ups()