from crac_server.component.ups.ups import Ups as UpsBase
from nut2 import PyNUTClient

class Ups(UpsBase):
    def __init__(self, host: str, login: str, password: str, time_expired: int) -> None:
        super().__init__(host, login, password, time_expired)
        self.hostname = host  # Usa il nome corretto
        self.login = login
        self.password = password
        self.time_expired = time_expired

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

            return client
        except Exception as e:
            # Cattura BrokenPipe o EOFError e solleva un ConnectionError
            raise ConnectionError(f"Impossibile connettersi o autenticarsi con NUT: {e}")

    def _read(self, device: str) -> dict[str,str]:
        client = self._get_client()
        return client.list_vars(device)

    def list_ups(self):
        client = self._get_client()
        # Non serve chiamare list_ups qui, è già stato fatto in _get_client()
        return client.list_ups()