from crac_server.component.ups.ups import Ups as UpsBase
from nut2 import PyNUTClient

class Ups(UpsBase):
    def __init__(self, host: str, port: int, login: str, password: str, time_expired: int) -> None:
        super().__init__(host, port, login, password, time_expired)
        self.hostname = host
        self.port = port
        self.login = login
        self.password = password
        self.time_expired = time_expired

    def _get_client(self):
        """
        Build a freshly authenticated client. A long lived one goes stale and
        fails with BrokenPipe or EOFError, reported here as a ConnectionError.
        """
        try:
            client = PyNUTClient(
                self.hostname,
                port=self.port,
                login=self.login,
                password=self.password,
                timeout=self.time_expired
            )
            client.list_ups()
            return client
        except Exception as e:
            raise ConnectionError(f"Impossibile connettersi o autenticarsi con NUT: {e}")

    def _read(self, device: str) -> dict[str,str]:
        return self._get_client().list_vars(device)

    def list_ups(self):
        return self._get_client().list_ups()
