import json
import logging
import socket
import threading
import time

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 1.0
# INDIGO chiude lato server le connessioni client silenziose da troppo
# tempo (misurato: timeout di lettura di ~5s, log "N -> // timeout" seguito
# da "Detach client"/"Closed"). Un client che si limita ad ascoltare, senza
# mai inviare nulla di suo finché l'utente non agisce, viene quindi chiuso
# periodicamente: serve un keep-alive attivo, ben sotto quei 5s di margine.
KEEPALIVE_INTERVAL = 2.0
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
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive_thread.start()

    def _keepalive_loop(self):
        while self._running:
            time.sleep(KEEPALIVE_INTERVAL)
            self._send_keepalive_ping()

    def _send_keepalive_ping(self):
        # getProperties senza filtro "device" è un ping innocuo e valido
        # per INDIGO indipendentemente da quali device siano connessi -
        # serve solo a generare traffico in uscita per non far scattare
        # il timeout di lettura lato server.
        self.send({"getProperties": {"version": 512}})

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
            with self._lock:
                self._connected_devices.clear()
        except OSError as e:
            logger.error(f"[IndigoClient] Connection to {self._hostname}:{self._port} failed: {e}")
            with self._socket_lock:
                self._socket = None

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
                logger.error(f"[IndigoClient] Read error: {e}")
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
            logger.debug(f"[IndigoClient] Sending {len(payload)} bytes: {payload[:200]}")
            sock.sendall(payload)
            return True
        except OSError as e:
            logger.error(f"[IndigoClient] Send error: {e}")
            self._drop_socket(sock)
            return False

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
        """Verifica se il device risulta gia' connesso lato INDIGO, senza
        mai forzarne la connessione (a differenza di connect_device()): usata
        dal telescopio, dove la connessione va stabilita dall'operatore dal
        pannello INDIGO prima che crac la usi, non innescata da crac stesso."""
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
