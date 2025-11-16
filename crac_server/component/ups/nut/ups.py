from crac_server.component.ups.ups import Ups as UpsBase
from nut2 import PyNUTClient

class Ups(UpsBase):
    def __init__(self, host: str, login: str, password: str, time_expired: int) -> None:
        super().__init__(host, login, password, time_expired)
        self.hostname = host  # Usa il nome corretto
        self.login = login
        self.password = password
        self.time_expired = time_expired
        #self.client = PyNUTClient(host,login=login,password=password,timeout=time_expired)
        '''
        try:
            # list_ups è un comando semplice e dovrebbe essere il primo ad essere chiamato
            self.client.list_ups() 
            print(f"DEBUG: Connessione NUT stabilita e autenticata su {host}:3493.")
        except Exception as e:
            # Cattura errori come Timeout, ConnectionRefused o BrokenPipe
            print(f"ERRORE NUT: Connessione o autenticazione fallita: {e}")
            raise ConnectionError(f"Impossibile connettersi/autenticarsi con NUT: {e}")
        '''
    def _get_client(self):
        """Metodo helper per creare e autenticare un client fresco."""
        try:
            client = PyNUTClient(
                self.hostname, # <-- Ora usa l'attributo che hai salvato!
                login=self.login,
                password=self.password,
                timeout=self.time_expired
            )
            # Forza l'autenticazione/connessione
            client.list_ups() 
            print("connected NUT client established and authenticated to {client.hostname}:3493.")

            return client
        except Exception as e:
            # Cattura BrokenPipe o EOFError e solleva un ConnectionError
            raise ConnectionError(f"Impossibile connettersi o autenticarsi con NUT: {e}")

    def status_for(self, device: str) -> dict[str,str]:
        # **1. CREA CLIENT FRESCO E AUTENTICA**
        client = self._get_client()

        # **2. Esegui la richiesta IMMEDIATAMENTE**
        raw_data = client.list_vars(device)
        print(f"DEBUG: Dati grezzi UPS per {device}: {raw_data}")

        # 3. Estrai i dati...
        return {
            'input_voltage': raw_data.get('input.voltage', '0.0'),
            'battery_charge': raw_data.get('battery.charge', '0'),
            'ups_status': raw_data.get('ups.status', 'UNKNOWN')
        }

    def list_ups(self):
        client = self._get_client()
        # Non serve chiamare list_ups qui, è già stato fatto in _get_client()
        return client.list_ups()