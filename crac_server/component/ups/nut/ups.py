from crac_server.component.ups.ups import Ups as UpsBase
from nut2 import PyNUTClient

class Ups(UpsBase):
    def __init__(self, host: str, login: str, password: str, time_expired: int) -> None:
        super().__init__(host, login, password, time_expired)
        self.client = PyNUTClient(
            host,
            login=login,
            password=password,
            timeout=time_expired
            )

    def status_for(self, device: str) -> dict[str,str]:
        raw_data = self.client.list_vars(device)

        # 2. Estrai solo i dati essenziali e rinomina le chiavi per coerenza
        return {
            'input_voltage': raw_data.get('input.voltage', '0.0'),
            'battery_charge': raw_data.get('battery.charge', '0'),
            'ups_status': raw_data.get('ups.status', 'UNKNOWN')
        }
        #return self.client.list_vars(device)

    def list_ups(self):
        return self.client.list_ups()