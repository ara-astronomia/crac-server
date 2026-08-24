import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.telescope_pb2 import AltazimutalCoords, TelescopeSpeed, TelescopeStatus
from crac_server.component.telescope.indigo.telescope import Telescope


class TestIndigoTelescope(unittest.TestCase):

    def setUp(self):
        patcher = patch("crac_server.component.telescope.indigo.telescope.get_indigo_client")
        self.addCleanup(patcher.stop)
        mock_get_client = patcher.start()
        self.mock_client = MagicMock()
        mock_get_client.return_value = self.mock_client
        self.telescope = Telescope(hostname="host", port=1)

    def _stub_properties(self, props: dict):
        def get_property(device, name, timeout=2.0):
            return props.get(name)
        self.mock_client.get_property.side_effect = get_property

    def test_init_does_not_force_connection_and_skips_raw_socket_polling(self):
        # la connessione va stabilita dall'operatore dal pannello INDIGO
        # prima che crac la usi, non forzata da crac stesso in __init__.
        self.mock_client.connect_device.assert_not_called()
        self.assertFalse(self.telescope._uses_raw_socket)

    def test_init_syncs_geographic_coordinates(self):
        # regressione: Mount Simulator parte a lat/lon 0°,0° finché non
        # gliela mandiamo - la stessa RA/DEC risulta a un'altitudine
        # completamente diversa da quella vista dal nostro calcolo (fatto
        # sulla posizione reale dell'osservatorio), facendo atterrare
        # qualunque slew (es. flat) nel punto sbagliato.
        sent = [c.args[0] for c in self.mock_client.send.call_args_list]
        geo = next(s["newNumberVector"] for s in sent if s.get("newNumberVector", {}).get("name") == "GEOGRAPHIC_COORDINATES")
        items = {i["name"]: i["value"] for i in geo["items"]}
        # crac_server/config.ini: lat = 42d13.76m, lon = +12d48.69m, height = 465
        self.assertAlmostEqual(items["LATITUDE"], 42.229333, places=3)
        self.assertAlmostEqual(items["LONGITUDE"], 12.8115, places=3)
        self.assertAlmostEqual(items["ELEVATION"], 465, places=3)

    def test_geographic_coordinates_retried_until_send_succeeds(self):
        # regressione: il send() in __init__ è fire-and-forget - se il
        # socket del client condiviso non è ancora pronto al primo
        # tentativo (stessa race di connect_device), senza ritentare la
        # sincronizzazione geografica fallirebbe in silenzio per sempre.
        patcher = patch("crac_server.component.telescope.indigo.telescope.get_indigo_client")
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.send.return_value = False
        mock_get_client.return_value = mock_client
        telescope = Telescope(hostname="host", port=1)
        self.assertFalse(telescope._geo_synced)

        mock_client.send.return_value = True
        mock_client.send.reset_mock()
        self._stub_properties_for(telescope, mock_client, {
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        telescope.retrieve()
        self.assertTrue(telescope._geo_synced)
        sent_names = [next(iter(c.args[0].values()))["name"] for c in mock_client.send.call_args_list]
        self.assertIn("GEOGRAPHIC_COORDINATES", sent_names)

    def _stub_properties_for(self, telescope, mock_client, props):
        mock_client.get_property.side_effect = lambda device, name, timeout=2.0: props.get(name)

    def test_retrieve_reconnects_device_on_every_cycle(self):
        # non basta farlo in __init__: se il client si riconnette e la cache
        # si svuota, senza questa richiamata ad ogni retrieve() il device
        # non verrebbe più ri-connesso e resterebbe bloccato per sempre.
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.telescope.retrieve()
        self.assertEqual(self.mock_client.connect_device.call_count, 2)

    def test_retrieve_refuses_when_device_not_connected_on_indigo(self):
        # in produzione l'operatore deve collegare il telescopio dal
        # pannello INDIGO prima che crac lo usi - crac non deve forzare la
        # connessione da solo, ne' fingere di essere connesso.
        self.mock_client.is_device_connected.return_value = False
        eq_coords, aa_coords, speed, status = self.telescope.retrieve()
        self.assertIsNone(eq_coords)
        self.assertIsNone(aa_coords)
        self.assertEqual(speed, TelescopeSpeed.SPEED_ERROR)
        self.assertEqual(status, TelescopeStatus.LOST)
        self.mock_client.connect_device.assert_not_called()

    def test_retrieve_reads_coordinates_and_speed_from_cache(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Ok", "items": [{"name": "RA", "value": 5.0}, {"name": "DEC", "value": 10.0}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 20.0}, {"name": "AZ", "value": 30.0}]},
            "MOUNT_TRACKING": {"items": [{"name": "ON", "value": True}]},
        })
        self.telescope._polling = True
        eq_coords, aa_coords, speed, _ = self.telescope.retrieve()
        self.assertEqual((eq_coords.ra, eq_coords.dec), (5.0, 10.0))
        self.assertEqual((aa_coords.alt, aa_coords.az), (20.0, 30.0))
        self.assertEqual(speed, TelescopeSpeed.SPEED_TRACKING)

    def test_retrieve_speed_not_tracking_when_tracking_off_and_state_ok(self):
        # regressione: indigo_mount_simulator.c non usa mai lo stato "Idle"
        # per MOUNT_EQUATORIAL_COORDINATES, solo "Ok"/"Busy"/"Alert" - con
        # tracking spento a riposo lo stato è comunque "Ok", non "Idle".
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Ok", "items": [{"name": "RA", "value": 5.0}, {"name": "DEC", "value": 10.0}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 20.0}, {"name": "AZ", "value": 30.0}]},
            "MOUNT_TRACKING": {"items": [{"name": "ON", "value": False}]},
        })
        self.telescope._polling = True
        _, _, speed, _ = self.telescope.retrieve()
        self.assertEqual(speed, TelescopeSpeed.SPEED_NOT_TRACKING)

    def test_retrieve_raises_when_coordinates_not_yet_cached(self):
        self._stub_properties({})
        with self.assertRaises(Exception):
            self.telescope.retrieve()

    def test_retrieve_status_disconnected_when_not_polling(self):
        self.telescope._polling = False
        status = self.telescope._retrieve_status(AltazimutalCoords(alt=0, az=0))
        self.assertEqual(status, TelescopeStatus.DISCONNECTED)

    def test_retrieve_status_parked(self):
        self._stub_properties({"MOUNT_PARK": {"items": [{"name": "PARKED", "value": True}]}})
        self.telescope._polling = True
        status = self.telescope._retrieve_status(AltazimutalCoords(alt=50, az=50))
        self.assertEqual(status, TelescopeStatus.PARKED)

    def test_retrieve_status_park_false_when_property_missing(self):
        self._stub_properties({})
        self.telescope._polling = True
        status = self.telescope._retrieve_status(AltazimutalCoords(alt=0, az=0))
        self.assertNotEqual(status, TelescopeStatus.PARKED)

    def test_park_sends_parked_command(self):
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        sent = self.mock_client.send.call_args[0][0]
        self.assertEqual(sent["newSwitchVector"]["name"], "MOUNT_PARK")
        items = {i["name"]: i["value"] for i in sent["newSwitchVector"]["items"]}
        self.assertEqual(items, {"PARKED": True, "UNPARKED": False})

    def test_set_speed_sends_on_coordinates_set_as_switch_vector_even_when_not_tracking(self):
        # regressione: MOUNT_ON_COORDINATES_SET è una proprietà switch, non
        # number - mandata come newNumberVector il driver la ignora e lo
        # slew di MOUNT_EQUATORIAL_COORDINATES non scatta mai. E va inviata
        # anche per SPEED_NOT_TRACKING (il caso reale di flat() in questa
        # config, dove has_tracking_off_capability=true): indigo_mount_
        # simulator.c implementa solo i rami TRACK e SYNC per il movimento,
        # quindi TRACK va selezionato per ottenere lo slew a prescindere dal
        # tracking continuo richiesto dopo l'arrivo (governato a parte da
        # MOUNT_TRACKING).
        self.telescope.set_speed(TelescopeSpeed.SPEED_NOT_TRACKING)
        sent = [c.args[0] for c in self.mock_client.send.call_args_list]
        coord_set = next(s["newSwitchVector"] for s in sent if s.get("newSwitchVector", {}).get("name") == "MOUNT_ON_COORDINATES_SET")
        items = {i["name"]: i["value"] for i in coord_set["items"]}
        self.assertEqual(items["TRACK"], True)
        tracking = next(s["newSwitchVector"] for s in sent if s.get("newSwitchVector", {}).get("name") == "MOUNT_TRACKING")
        tracking_items = {i["name"]: i["value"] for i in tracking["items"]}
        self.assertEqual(tracking_items, {"ON": False, "OFF": True})

    def test_flat_unparks_before_moving(self):
        self._stub_properties({"MOUNT_EQUATORIAL_COORDINATES": {"state": "Ok"}})
        sent_calls = []
        self.mock_client.send.side_effect = lambda script: sent_calls.append(script) or True
        self.telescope.flat(TelescopeSpeed.SPEED_NOT_TRACKING)
        names_in_order = [
            next(iter(s.values()))["name"] for s in sent_calls
        ]
        self.assertIn("MOUNT_PARK", names_in_order)
        self.assertIn("MOUNT_ON_COORDINATES_SET", names_in_order)
        self.assertIn("MOUNT_EQUATORIAL_COORDINATES", names_in_order)
        # l'ordine conta: il driver controlla MOUNT_ON_COORDINATES_SET.TRACK
        # nello stesso istante in cui riceve il cambio di coordinate, quindi
        # deve arrivare prima, non dopo (né in coda per il ciclo successivo).
        self.assertLess(
            names_in_order.index("MOUNT_PARK"),
            names_in_order.index("MOUNT_EQUATORIAL_COORDINATES"),
        )
        self.assertLess(
            names_in_order.index("MOUNT_ON_COORDINATES_SET"),
            names_in_order.index("MOUNT_EQUATORIAL_COORDINATES"),
        )

    def test_flat_turns_tracking_off_only_after_slew_completes(self):
        # regressione: indigo_mount_simulator.c riaccende MOUNT_TRACKING in
        # automatico appena lo slew finisce (se era spento quando avviato) -
        # un OFF mandato subito verrebbe sovrascritto. Va aspettato lo stato
        # non-Busy prima di spegnerlo di nuovo. Il primo stato "Ok" simula
        # la cache non ancora aggiornata subito dopo l'invio delle
        # coordinate (misurato: bastava <1ms per leggere lo stato vecchio) -
        # va aspettato che diventi Busy prima di aspettare che torni Ok,
        # altrimenti si esce subito leggendo lo stato pre-comando.
        states = iter([{"state": "Ok"}, {"state": "Busy"}, {"state": "Busy"}, {"state": "Ok"}])
        self.mock_client.get_property.side_effect = lambda device, name, timeout=2.0: next(states)
        with patch("crac_server.component.telescope.indigo.telescope.time.sleep"):
            self.telescope.flat(TelescopeSpeed.SPEED_NOT_TRACKING)
        self.assertEqual(self.mock_client.get_property.call_count, 4)
        sent = [c.args[0] for c in self.mock_client.send.call_args_list]
        last_tracking = [s for s in sent if s.get("newSwitchVector", {}).get("name") == "MOUNT_TRACKING"][-1]
        items = {i["name"]: i["value"] for i in last_tracking["newSwitchVector"]["items"]}
        self.assertEqual(items, {"ON": False, "OFF": True})
