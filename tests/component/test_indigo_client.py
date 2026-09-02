import unittest
from unittest.mock import MagicMock, patch

from crac_server.component.indigo_client import IndigoClient, get_indigo_client, _clients


class TestIndigoClient(unittest.TestCase):

    def setUp(self):
        patcher = patch("crac_server.component.indigo_client.threading.Thread")
        self.addCleanup(patcher.stop)
        patcher.start()
        self.client = IndigoClient(hostname="test-host", port=1234)
        self.client._socket = MagicMock()

    def test_keepalive_ping_sends_get_properties(self):
        # regressione: INDIGO chiude lato server le connessioni client
        # silenziose per troppo tempo (misurato: timeout di lettura ~5s,
        # log "N -> // timeout" seguito da "Detach client"/"Closed"). Un
        # client che parla solo su azione utente va tenuto vivo attivamente.
        self.client._send_keepalive_ping()
        sent = self.client._socket.sendall.call_args[0][0]
        self.assertIn(b'"getProperties"', sent)

    def test_connect_clears_read_timeout_after_connecting(self):
        # regressione: create_connection(timeout=5) lascia il timeout attivo
        # anche sulle recv() successive, facendo scadere il thread di lettura
        # ogni volta che INDIGO resta silenzioso per 5s e causando reconnect
        # continui scambiati per errori di connessione.
        mock_socket = MagicMock()
        with patch("crac_server.component.indigo_client.socket.create_connection", return_value=mock_socket):
            self.client._connect()
        mock_socket.settimeout.assert_called_once_with(None)

    def test_handle_message_caches_def_vector(self):
        self.client._handle_message({
            "defSwitchVector": {"device": "Dev", "name": "AUX_COVER", "items": [{"name": "OPEN", "value": True}]}
        })
        prop = self.client.get_property("Dev", "AUX_COVER", timeout=0)
        self.assertEqual(prop["items"][0]["name"], "OPEN")

    def test_handle_message_updates_on_set_vector(self):
        self.client._handle_message({"defSwitchVector": {"device": "Dev", "name": "P", "items": []}})
        self.client._handle_message({"setSwitchVector": {"device": "Dev", "name": "P", "items": [{"name": "X", "value": 1}]}})
        prop = self.client.get_property("Dev", "P", timeout=0)
        self.assertEqual(prop["items"], [{"name": "X", "value": 1}])

    def test_partial_set_vector_preserves_previously_known_items(self):
        # regressione: INDIGO manda spesso solo l'item cambiato (es. un
        # setNumberVector con solo RA, senza DEC) - sostituire di netto la
        # proprietà in cache perdeva i valori non toccati da quell'update.
        self.client._handle_message({
            "defNumberVector": {"device": "Dev", "name": "COORDS", "state": "Ok",
                                 "items": [{"name": "RA", "value": 1.0}, {"name": "DEC", "value": 2.0}]}
        })
        self.client._handle_message({
            "setNumberVector": {"device": "Dev", "name": "COORDS", "state": "Ok",
                                 "items": [{"name": "RA", "value": 1.5}]}
        })
        prop = self.client.get_property("Dev", "COORDS", timeout=0)
        items = {i["name"]: i["value"] for i in prop["items"]}
        self.assertEqual(items, {"RA": 1.5, "DEC": 2.0})

    def test_handle_message_ignores_unrelated_keys(self):
        self.client._handle_message({"getProperties": {"device": "Dev", "name": "P"}})
        self.assertIsNone(self.client.get_property("Dev", "P", timeout=0))

    def test_get_property_missing_returns_none_after_timeout(self):
        result = self.client.get_property("Dev", "Missing", timeout=0.05)
        self.assertIsNone(result)

    def test_send_writes_json_with_trailing_newline(self):
        self.client.send({"newSwitchVector": {"device": "Dev"}})
        sent = self.client._socket.sendall.call_args[0][0]
        self.assertIn(b'"device": "Dev"', sent)
        self.assertTrue(sent.endswith(b"\n"))

    def test_send_returns_false_and_drops_socket_on_error(self):
        self.client._socket.sendall.side_effect = OSError("boom")
        result = self.client.send({"foo": "bar"})
        self.assertFalse(result)
        self.assertIsNone(self.client._socket)

    def test_send_without_connection_returns_false(self):
        self.client._socket = None
        self.assertFalse(self.client.send({"foo": "bar"}))

    def test_connect_device_sends_connection_and_get_properties_once(self):
        # deve inviare entrambe: il solo CONNECTION non basta se il device
        # risultava già connesso lato INDIGO (indigo_ignore_connection_change
        # lo tratta da no-op e non ri-espone le proprietà al nuovo client).
        self.client.connect_device("Dev")
        self.client.connect_device("Dev")
        self.assertEqual(self.client._socket.sendall.call_count, 2)
        sent_messages = [c.args[0] for c in self.client._socket.sendall.call_args_list]
        self.assertTrue(any(b'"CONNECTED"' in m for m in sent_messages))
        self.assertTrue(any(b'"getProperties"' in m for m in sent_messages))

    def test_connect_device_not_marked_connected_if_send_fails(self):
        self.client._socket.sendall.side_effect = OSError("boom")
        self.client.connect_device("Dev")
        self.assertNotIn("Dev", self.client._connected_devices)
        # un tentativo successivo (es. dopo una riconnessione) deve ritentare,
        # non restare bloccato per sempre
        self.client._socket = MagicMock()
        self.client.connect_device("Dev")
        self.assertIn("Dev", self.client._connected_devices)


class TestGetIndigoClient(unittest.TestCase):

    def setUp(self):
        patcher = patch("crac_server.component.indigo_client.threading.Thread")
        self.addCleanup(patcher.stop)
        patcher.start()
        _clients.clear()

    def test_returns_singleton_per_host_and_port(self):
        first = get_indigo_client("host", 1)
        second = get_indigo_client("host", 1)
        third = get_indigo_client("host", 2)
        self.assertIs(first, second)
        self.assertIsNot(first, third)
