import socket
import unittest
from unittest.mock import MagicMock, patch

from crac_server.component.client.indigo import IndigoClient, get_indigo_client, _clients


class TestIndigoClient(unittest.TestCase):

    def setUp(self):
        patcher = patch("crac_server.component.client.indigo.threading.Thread")
        self.addCleanup(patcher.stop)
        patcher.start()
        self.client = IndigoClient(hostname="test-host", port=1234)
        self.client._socket = MagicMock()
        self.sent = []
        self.client._socket.sendall.side_effect = self.sent.append

    def test_is_device_connected_reads_the_cache_without_asking_indigo(self):
        self.client._handle_message({
            "defSwitchVector": {"device": "Dev", "name": "CONNECTION",
                                "items": [{"name": "CONNECTED", "value": True}]}
        })
        self.assertTrue(self.client.is_device_connected("Dev"))
        self.assertEqual(self.sent, [])

    def test_is_device_connected_asks_once_when_the_cache_is_empty(self):
        self.assertFalse(self.client.is_device_connected("Dev", timeout=0))
        self.assertEqual(len(self.sent), 1)
        self.assertIn(b'"CONNECTION"', self.sent[0])

    def test_connect_clears_read_timeout_after_connecting(self):
        # regressione: create_connection(timeout=5) lascia il timeout attivo
        # anche sulle recv() successive, facendo scadere il thread di lettura
        # ogni volta che INDIGO resta silenzioso per 5s e causando reconnect
        # continui scambiati per errori di connessione.
        mock_socket = MagicMock()
        with patch("crac_server.component.client.indigo.socket.create_connection", return_value=mock_socket):
            self.client._connect()
        mock_socket.settimeout.assert_called_once_with(None)

    def test_connect_clears_the_properties_cache(self):
        self.client._handle_message({"defSwitchVector": {"device": "Dev", "name": "CONNECTION", "items": []}})
        with patch("crac_server.component.client.indigo.socket.create_connection", return_value=MagicMock()):
            self.client._connect()
        self.assertIsNone(self.client.get_property("Dev", "CONNECTION", timeout=0))

    def test_reconnect_closes_the_socket_and_clears_the_cache(self):
        self.client._handle_message({
            "defSwitchVector": {"device": "Dev", "name": "CONNECTION",
                                "items": [{"name": "CONNECTED", "value": True}]}
        })
        stale_socket = self.client._socket
        self.client._connected_devices.add("Dev")

        self.client.reconnect()

        # shutdown() before close(): a thread blocked in recv() with no
        # timeout on this socket isn't guaranteed to wake up from close()
        # alone (unspecified by POSIX, often a no-op on Linux for a fd
        # closed from a different thread) - shutdown() reliably does.
        stale_socket.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        stale_socket.close.assert_called_once()
        call_order = [c[0] for c in stale_socket.method_calls]
        self.assertEqual(call_order, ["shutdown", "close"])
        self.assertIsNone(self.client._socket)
        self.assertIsNone(self.client.get_property("Dev", "CONNECTION", timeout=0))
        self.assertEqual(self.client._connected_devices, set())
        self.assertEqual(self.client.seconds_since_last_message("Dev"), float("inf"))

    def test_seconds_since_last_message_can_be_asked_about_one_device(self):
        self.client._handle_message({
            "defSwitchVector": {"device": "Dev", "name": "P", "items": []}
        })
        self.assertLess(self.client.seconds_since_last_message("Dev"), 1.0)
        self.assertEqual(self.client.seconds_since_last_message("OtherDev"), float("inf"))

    def test_seconds_since_last_message_is_infinite_before_anything_arrives(self):
        self.assertEqual(self.client.seconds_since_last_message(), float("inf"))

    def test_seconds_since_last_message_resets_on_any_message_from_any_device(self):
        self.client._handle_message({"defSwitchVector": {"device": "Dev", "name": "P", "items": []}})
        self.assertLess(self.client.seconds_since_last_message(), 1.0)

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

    def test_delete_property_with_name_removes_only_that_property(self):
        self.client._handle_message({"defSwitchVector": {"device": "Dev", "name": "CONNECTION", "items": []}})
        self.client._handle_message({"defSwitchVector": {"device": "Dev", "name": "AUX_COVER", "items": []}})
        self.client._handle_message({"deleteProperty": {"device": "Dev", "name": "CONNECTION"}})
        self.assertIsNone(self.client.get_property("Dev", "CONNECTION", timeout=0))
        self.assertIsNotNone(self.client.get_property("Dev", "AUX_COVER", timeout=0))

    def test_delete_property_without_name_removes_the_whole_device(self):
        self.client._handle_message({"defSwitchVector": {"device": "Dev", "name": "CONNECTION", "items": []}})
        self.client._handle_message({"defSwitchVector": {"device": "Dev", "name": "AUX_COVER", "items": []}})
        self.client._handle_message({"defSwitchVector": {"device": "OtherDev", "name": "CONNECTION", "items": []}})
        self.client._handle_message({"deleteProperty": {"device": "Dev"}})
        self.assertIsNone(self.client.get_property("Dev", "CONNECTION", timeout=0))
        self.assertIsNone(self.client.get_property("Dev", "AUX_COVER", timeout=0))
        self.assertIsNotNone(self.client.get_property("OtherDev", "CONNECTION", timeout=0))

    def test_get_property_missing_returns_none_after_timeout(self):
        result = self.client.get_property("Dev", "Missing", timeout=0.05)
        self.assertIsNone(result)

    def test_send_writes_json_with_trailing_newline(self):
        self.client.send({"newSwitchVector": {"device": "Dev"}})
        sent = self.client._socket.sendall.call_args[0][0]
        self.assertIn(b'"device": "Dev"', sent)
        self.assertTrue(sent.endswith(b"\n"))

    def test_send_logs_every_call_to_indigo_at_info(self):
        with self.assertLogs("crac_server.component.client.indigo", level="INFO") as logs:
            self.client.send({"getProperties": {"version": 512, "device": "Dev", "name": "CONNECTION"}})
        self.assertIn("getProperties Dev CONNECTION", logs.output[0])

    def test_send_returns_false_and_drops_socket_on_error(self):
        self.client._socket.sendall.side_effect = OSError("boom")
        result = self.client.send({"foo": "bar"})
        self.assertFalse(result)
        self.assertIsNone(self.client._socket)

    def test_send_without_connection_returns_false(self):
        self.client._socket = None
        self.assertFalse(self.client.send({"foo": "bar"}))

    def test_a_command_dropped_for_lack_of_connection_is_logged(self):
        self.client._socket = None
        with self.assertLogs("crac_server.component.client.indigo", level="WARNING") as logs:
            self.client.send({"newSwitchVector": {"device": "Dev", "name": "MOUNT_PARK"}})
        self.assertIn("newSwitchVector Dev MOUNT_PARK", logs.output[0])

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
        patcher = patch("crac_server.component.client.indigo.threading.Thread")
        self.addCleanup(patcher.stop)
        patcher.start()
        _clients.clear()

    def test_returns_singleton_per_host_and_port(self):
        first = get_indigo_client("host", 1)
        second = get_indigo_client("host", 1)
        third = get_indigo_client("host", 2)
        self.assertIs(first, second)
        self.assertIsNot(first, third)


class TestIndigoClientConnectionLogging(unittest.TestCase):

    LOGGER = "crac_server.component.client.indigo"

    def setUp(self):
        patcher = patch("crac_server.component.client.indigo.threading.Thread")
        self.addCleanup(patcher.stop)
        patcher.start()
        self.client = IndigoClient(hostname="test-host", port=1234)

    def _connection_refused(self):
        return patch(
            "crac_server.component.client.indigo.socket.create_connection",
            side_effect=OSError("connection refused"),
        )

    def test_a_failure_retried_every_second_is_logged_once(self):
        with self._connection_refused():
            with self.assertLogs(self.LOGGER, level="ERROR") as captured:
                for _ in range(30):
                    self.client._connect()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("[IndigoClient]", message)
        self.assertIn("device_unreachable", message)
        self.assertIn("connection refused", message)

    def test_reconnection_after_a_failure_is_logged(self):
        with self._connection_refused():
            self.client._connect()
        with patch("crac_server.component.client.indigo.socket.create_connection"):
            with self.assertLogs(self.LOGGER, level="INFO") as captured:
                self.client._connect()
        self.assertTrue(any("recovered" in r.getMessage() for r in captured.records))

    def test_a_new_failure_after_a_reconnection_is_logged_again(self):
        with self._connection_refused():
            self.client._connect()
        with patch("crac_server.component.client.indigo.socket.create_connection"):
            self.client._connect()
        with self._connection_refused():
            with self.assertLogs(self.LOGGER, level="ERROR") as captured:
                self.client._connect()
        self.assertEqual(len(captured.records), 1)

    def test_a_dropped_connection_and_the_failed_retries_are_one_transition(self):
        with self.assertLogs(self.LOGGER, level="ERROR") as captured:
            self.client._on_read_failure(ConnectionError("connection closed by peer"))
            with self._connection_refused():
                for _ in range(10):
                    self.client._connect()
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("device_unreachable", message)
        self.assertIn("connection closed by peer", message)
