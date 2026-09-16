import json
import logging
import socket
import threading
import time

from crac_server.status_log import ErrorCause, StatusLogger

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 1.0
CONNECTION_PROPERTY = {
    "name": "CONNECTION",
    "items": [
        {"name": "CONNECTED", "value": True},
        {"name": "DISCONNECTED", "value": False},
    ],
}


class IndigoClient:
    """
    Client INDIGO condiviso: una sola connessione TCP persistente, un thread
    che la legge in continuo aggiornando una cache locale delle proprietà
    (INDIGO spinge autonomamente i def/setXXXVector, non serve fare polling
    via reconnect) e un metodo send() per i comandi (newXXXVector).
    """

    def __init__(self, hostname: str, port: int) -> None:
        self._hostname = hostname
        self._port = port
        self._socket = None
        # Protegge self._socket da letture/scritture/riassegnazioni
        # concorrenti tra il thread di lettura e i chiamanti di send() -
        # senza, un send() fallito su un socket ormai sostituito da una
        # riconnessione più recente può azzerare per errore quello nuovo.
        self._socket_lock = threading.Lock()
        self._properties = {}
        self._connected_devices = set()
        self._status_log = StatusLogger(logger, "IndigoClient")
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _connect(self):
        try:
            sock = socket.create_connection((self._hostname, self._port), timeout=5)
            # Il timeout sopra vale solo per la connect(): il thread di
            # lettura deve poter restare bloccato in recv() senza scadere
            # ogni volta che INDIGO non ha nulla di nuovo da inviare.
            sock.settimeout(None)
            with self._socket_lock:
                self._socket = sock
            logger.info(f"[IndigoClient] Connected to {self._hostname}:{self._port}")
            self._status_log.record("CONNECTED")
            with self._lock:
                self._connected_devices.clear()
        except OSError as e:
            self._status_log.record(
                "DISCONNECTED", ErrorCause.DEVICE_UNREACHABLE,
                detail=f"{self._hostname}:{self._port}: {e}",
            )
            with self._socket_lock:
                self._socket = None

    def _on_read_failure(self, error: Exception) -> None:
        """A dropped connection and the failed retries that follow are one
        outage: recording them under the same cause keeps the reason the
        connection actually died - which only this point knows - and leaves
        the retries silent."""
        self._status_log.record(
            "DISCONNECTED", ErrorCause.DEVICE_UNREACHABLE,
            detail=f"{self._hostname}:{self._port}: {error}",
        )

    def _drop_socket(self, sock):
        """Azzera self._socket solo se è ancora quello fallito: una
        riconnessione nel frattempo avvenuta non va persa."""
        with self._socket_lock:
            if self._socket is sock:
                self._socket = None

    def _read_loop(self):
        decoder = json.JSONDecoder()
        buffer = ""
        while self._running:
            with self._socket_lock:
                sock = self._socket
            if sock is None:
                self._connect()
                if self._socket is None:
                    time.sleep(RECONNECT_DELAY)
                continue
            try:
                data = sock.recv(65536)
                if not data:
                    raise ConnectionError("connection closed by peer")
                logger.debug(f"[IndigoClient] Received {len(data)} bytes")
                buffer += data.decode("utf-8", errors="ignore")
            except (OSError, ConnectionError) as e:
                self._on_read_failure(e)
                self._drop_socket(sock)
                buffer = ""
                time.sleep(RECONNECT_DELAY)
                continue

            while True:
                buffer = buffer.lstrip()
                if not buffer:
                    break
                try:
                    message, index = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    break
                buffer = buffer[index:]
                logger.debug(f"[IndigoClient] Parsed message: {message}")
                self._handle_message(message)

    def _handle_message(self, message: dict):
        for key, vector in message.items():
            if key[:3] not in ("def", "set"):
                continue
            device = vector.get("device")
            name = vector.get("name")
            if not device or not name:
                continue
            with self._lock:
                existing = self._properties.get((device, name))
                self._properties[(device, name)] = self._merge_property(existing, vector)

    @staticmethod
    def _merge_property(existing: dict | None, update: dict) -> dict:
        """INDIGO manda spesso aggiornamenti parziali (es. un setNumberVector
        con solo l'item RA cambiato, senza DEC) - sostituire di netto la
        proprietà in cache perderebbe i valori non toccati da quell'update.
        Si fondono solo gli item effettivamente presenti nel messaggio."""
        if existing is None:
            return update
        merged_items = {item["name"]: item for item in existing.get("items", [])}
        for item in update.get("items", []):
            merged_items[item["name"]] = item
        return {**existing, **update, "items": list(merged_items.values())}

    def send(self, script: dict) -> bool:
        with self._socket_lock:
            sock = self._socket
        if sock is None:
            # Non e' un guasto: il socket lo apre il thread di lettura in modo
            # asincrono, quindi un send() partito subito dopo la creazione del
            # client lo trova ancora None. Il chiamante riceve False e ritenta,
            # e una connessione davvero fallita e' gia' loggata a ERROR da
            # _connect(). Vedi issue sulla connessione iniziale del device.
            logger.debug("[IndigoClient] Cannot send, not connected")
            return False
        try:
            payload = json.dumps(script).encode("utf-8") + b"\n"
            logger.info(f"[IndigoClient] Sending {self._describe(script)}")
            sock.sendall(payload)
            return True
        except OSError as e:
            logger.error(f"[IndigoClient] Send error: {e}")
            self._drop_socket(sock)
            return False

    @staticmethod
    def _describe(script: dict) -> str:
        """The operation and the property it targets, e.g. "getProperties
        Mount LX200 CONNECTION": one readable line per call, so what crac
        asks INDIGO stays countable in the log at INFO."""
        operation, vector = next(iter(script.items()))
        fields = vector if isinstance(vector, dict) else {}
        return " ".join(str(part) for part in (operation, fields.get("device"), fields.get("name")) if part)

    def connect_device(self, device: str) -> bool:
        """Connette il device e ne richiede le proprietà, una sola volta per
        connessione fisica (self._connected_devices viene svuotato ad ogni
        riconnessione). Il solo comando CONNECTION non basta: se il device è
        già connesso lato INDIGO (es. sessione precedente), il driver lo
        considera un no-op (indigo_ignore_connection_change) e non
        ri-espone le sue proprietà al nuovo client - va sempre affiancato da
        una getProperties esplicita, che invece funziona indipendentemente
        dallo stato di connessione già in corso.

        Ritorna True se è stata effettuata una (ri)connessione reale, False
        se il device risultava già connesso su questa connessione fisica -
        utile ai chiamanti che devono ripetere una sincronizzazione one-shot
        andata persa insieme allo stato del device (es. indigo_server
        riavviato mentre crac-server resta in esecuzione).
        """
        with self._lock:
            if device in self._connected_devices:
                return False
        sent = self.send({"newSwitchVector": {"device": device, **CONNECTION_PROPERTY}})
        sent = self.send({"getProperties": {"version": 512, "device": device}}) and sent
        if sent:
            with self._lock:
                self._connected_devices.add(device)
        return sent

    def is_device_connected(self, device: str, timeout: float = 3.0) -> bool:
        """Tell whether INDIGO already holds the device connected, without
        ever connecting it (unlike connect_device()): the telescope is
        connected by the operator from the INDIGO panel, never by crac.

        The request goes out only while CONNECTION is missing from the cache:
        INDIGO pushes every later change on its own."""
        prop = self.get_property(device, "CONNECTION", timeout=0)
        if prop is None:
            self.send({"getProperties": {"version": 512, "device": device, "name": "CONNECTION"}})
            prop = self.get_property(device, "CONNECTION", timeout=timeout)
        if not prop:
            return False
        for item in prop.get("items", []):
            if item.get("name") == "CONNECTED":
                return bool(item.get("value"))
        return False

    def get_property(self, device: str, name: str, timeout: float = 2.0) -> dict | None:
        """Legge una proprietà dalla cache, attendendo brevemente se non è
        ancora arrivata (es. subito dopo connect_device())."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                prop = self._properties.get((device, name))
            if prop is not None or time.monotonic() >= deadline:
                return prop
            time.sleep(0.05)


_clients: dict[tuple[str, int], IndigoClient] = {}
_clients_lock = threading.Lock()


def get_indigo_client(hostname: str, port: int) -> IndigoClient:
    key = (hostname, port)
    with _clients_lock:
        if key not in _clients:
            _clients[key] = IndigoClient(hostname, port)
        return _clients[key]
