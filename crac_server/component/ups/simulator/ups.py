import os
from configparser import ConfigParser
from crac_server.component.ups.ups import Ups as UpsBase


class Ups(UpsBase):
    def __init__(self, host: str, login: str, password: str, time_expired: int) -> None:
        super().__init__(host, login, password, time_expired)
    
    def _read(self, device: str) -> dict[str,str]:
        ups_path = os.path.join(os.path.dirname(__file__), "ups.ini")
        ups_config = ConfigParser()
        ups_config.read(ups_path)
        if ups_config.getboolean(device, "fail", fallback=False):
            raise ConnectionError(f"UPS simulato {device}: fail=true in ups.ini")
        values = {
            "input.voltage": ups_config.get(device, "input.voltage", fallback='220'),
            "battery.charge": ups_config.get(device, "battery.charge", fallback='100'),
            "ups.status": ups_config.get(device, "ups.status", fallback='OL'),
            "output.current": ups_config.get(device, "output.current", fallback='0.00'),
        }
        ups_config[device] = values
        with open(ups_path, 'w') as ups_file:
            ups_config.write(ups_file)
        return values
