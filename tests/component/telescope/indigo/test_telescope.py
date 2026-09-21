import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.telescope_pb2 import AltazimutalCoords, EquatorialCoords, TelescopeSpeed, TelescopeStatus
from crac_server.component.telescope.indigo.telescope import LOST_AFTER_SECONDS, Telescope


class ImmediateThread:
    """Stand-in for threading.Thread that runs its target synchronously on
    .start() - retrieve() dispatches the stale-connection shutdown to a
    throwaway thread precisely so it isn't self.t joining itself, but a
    test has no reason to depend on real scheduling to observe the result."""

    def __init__(self, target, daemon=True):
        self._target = target

    def start(self):
        self._target()


class TestIndigoTelescope(unittest.TestCase):

    def setUp(self):
        patcher = patch("crac_server.component.telescope.indigo.telescope.get_indigo_client")
        self.addCleanup(patcher.stop)
        mock_get_client = patcher.start()
        self.mock_client = MagicMock()
        mock_get_client.return_value = self.mock_client
        # a bare MagicMock's __gt__ would make `seconds_since_last_message()
        # > STALE_CONNECTION_SECONDS` truthy by default, forcing every test
        # through the reconnect branch - a fresh connection is the normal
        # case, so it's the sane default here.
        self.mock_client.seconds_since_last_message.return_value = 0.0
        self.sent_scripts = []
        self.mock_client.send.side_effect = lambda script: self.sent_scripts.append(script) or True
        self.telescope = Telescope(hostname="host", port=1)

    def _stub_properties(self, props: dict):
        def get_property(device, name, timeout=2.0):
            return props.get(name)
        self.mock_client.get_property.side_effect = get_property

    def _sent_property_names(self):
        """Names of the properties sent to INDIGO, in order."""
        return [vector["name"] for script in self.sent_scripts for vector in script.values()]

    def test_a_queued_command_says_so(self):
        with self.assertLogs("crac_server.component.telescope.telescope", level="INFO") as logs:
            self.telescope.queue_park()
        self.assertIn("park queued", logs.output[0])

    def test_a_mount_at_rest_on_idle_coordinates_is_not_an_error(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Idle", "items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
            "MOUNT_TRACKING": {"items": [{"name": "ON", "value": False}]},
        })
        _, _, speed, _ = self.telescope.retrieve()
        self.assertEqual(speed, TelescopeSpeed.SPEED_NOT_TRACKING)

    def test_init_does_not_force_connection_and_skips_raw_socket_polling(self):
        self.mock_client.connect_device.assert_not_called()
        self.assertFalse(self.telescope._uses_raw_socket)

    def test_geographic_coordinates_are_never_sent_to_the_mount(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.assertNotIn("GEOGRAPHIC_COORDINATES", self._sent_property_names())

    def test_retrieve_reconnects_device_on_every_cycle(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.telescope.retrieve()
        self.assertEqual(self.mock_client.connect_device.call_count, 2)

    def _stub_clock(self):
        """Give the test a writable monotonic clock, so the hysteresis window
        is crossed by moving time instead of sleeping through it."""
        now = [0.0]
        patcher = patch("time.monotonic", lambda: now[0])
        self.addCleanup(patcher.stop)
        patcher.start()
        return now

    def _stub_last_known_state(self):
        self.telescope.eq_coords = EquatorialCoords(ra=1.0, dec=2.0)
        self.telescope.aa_coords = AltazimutalCoords(alt=3.0, az=4.0)
        self.telescope.speed = TelescopeSpeed.SPEED_TRACKING
        self.telescope._status = TelescopeStatus.SECURE

    def test_retrieve_keeps_the_last_known_state_on_a_single_failed_read(self):
        self._stub_clock()
        self._stub_last_known_state()
        self.mock_client.is_device_connected.return_value = False
        eq_coords, aa_coords, speed, status = self.telescope.retrieve()
        self.assertEqual(eq_coords, EquatorialCoords(ra=1.0, dec=2.0))
        self.assertEqual(aa_coords, AltazimutalCoords(alt=3.0, az=4.0))
        self.assertEqual(speed, TelescopeSpeed.SPEED_TRACKING)
        self.assertEqual(status, TelescopeStatus.SECURE)
        self.mock_client.connect_device.assert_not_called()

    def test_retrieve_declares_the_telescope_lost_past_the_hysteresis_window(self):
        now = self._stub_clock()
        self._stub_last_known_state()
        self.mock_client.is_device_connected.return_value = False
        self.telescope.retrieve()
        now[0] = LOST_AFTER_SECONDS + 0.1
        eq_coords, aa_coords, speed, status = self.telescope.retrieve()
        self.assertIsNone(eq_coords)
        self.assertIsNone(aa_coords)
        self.assertEqual(speed, TelescopeSpeed.SPEED_ERROR)
        self.assertEqual(status, TelescopeStatus.LOST)
        self.mock_client.connect_device.assert_not_called()

    def test_a_successful_read_restarts_the_hysteresis_window(self):
        now = self._stub_clock()
        self._stub_last_known_state()
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Ok", "items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
            "MOUNT_TRACKING": {"items": [{"name": "ON", "value": True}]},
        })
        self.mock_client.is_device_connected.return_value = False
        self.telescope.retrieve()
        now[0] = 1.0
        self.mock_client.is_device_connected.return_value = True
        self.telescope.retrieve()
        now[0] = 2.5
        self.mock_client.is_device_connected.return_value = False
        _, _, _, status = self.telescope.retrieve()
        self.assertNotEqual(status, TelescopeStatus.LOST)

    def _stub_staleness(self, device_quiet: float, bus_quiet: float):
        def seconds_since_last_message(device=None):
            return device_quiet if device else bus_quiet
        self.mock_client.seconds_since_last_message.side_effect = seconds_since_last_message

    def test_retrieve_reconnects_the_shared_client_without_stopping_polling(self):
        """A reconnect() already leaves the shared client healthy - stopping
        polling too would force a manual reconnect for a problem the code
        just fixed on its own."""
        self.telescope._polling = True
        self._stub_staleness(device_quiet=20.0, bus_quiet=20.0)
        with patch("crac_server.component.telescope.indigo.telescope.threading.Thread", ImmediateThread), \
             patch.object(self.telescope, "polling_end") as mock_polling_end:
            eq_coords, aa_coords, speed, status = self.telescope.retrieve()
        self.mock_client.reconnect.assert_called_once()
        self.assertIsNone(eq_coords)
        self.assertIsNone(aa_coords)
        self.assertEqual(speed, TelescopeSpeed.SPEED_ERROR)
        self.assertEqual(status, TelescopeStatus.DISCONNECTED)
        mock_polling_end.assert_not_called()

    def test_retrieve_disconnects_without_touching_the_shared_client_when_only_this_device_is_dead(self):
        self.telescope._polling = True
        self._stub_staleness(device_quiet=20.0, bus_quiet=0.0)
        with patch("crac_server.component.telescope.indigo.telescope.threading.Thread", ImmediateThread), \
             patch.object(self.telescope, "polling_end") as mock_polling_end:
            eq_coords, aa_coords, speed, status = self.telescope.retrieve()
        self.mock_client.reconnect.assert_not_called()
        self.assertIsNone(eq_coords)
        self.assertIsNone(aa_coords)
        self.assertEqual(speed, TelescopeSpeed.SPEED_ERROR)
        self.assertEqual(status, TelescopeStatus.DISCONNECTED)
        mock_polling_end.assert_called_once()

    def test_retrieve_checks_staleness_of_this_device_first(self):
        self._stub_staleness(device_quiet=0.0, bus_quiet=10.0)
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        with patch("crac_server.component.telescope.indigo.telescope.threading.Thread", ImmediateThread), \
             patch.object(self.telescope, "polling_end") as mock_polling_end:
            self.telescope.retrieve()
        self.mock_client.reconnect.assert_not_called()
        mock_polling_end.assert_not_called()
        self.mock_client.seconds_since_last_message.assert_any_call(self.telescope._name)

    def test_retrieve_does_not_reconnect_when_the_socket_is_fresh(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.mock_client.reconnect.assert_not_called()

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
        self._stub_park_properties()
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        sent = self.sent_scripts[-1]
        self.assertEqual(sent["newSwitchVector"]["name"], "MOUNT_PARK")
        items = {i["name"]: i["value"] for i in sent["newSwitchVector"]["items"]}
        self.assertEqual(items, {"PARKED": True, "UNPARKED": False})

    def _stub_park_properties(self, extra: dict | None = None):
        """Stub a park slew that completes at once: Busy, then Ok."""
        states = iter([{"state": "Busy"}, {"state": "Ok"}])
        props = dict(extra or {})

        def get_property(device, name, timeout=2.0):
            if name == "MOUNT_EQUATORIAL_COORDINATES":
                return next(states, {"state": "Ok"})
            return props.get(name)

        self.mock_client.get_property.side_effect = get_property

    def test_park_does_not_unpark_first(self):
        self._stub_park_properties()
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        parks = [
            {i["name"]: i["value"] for i in s["newSwitchVector"]["items"]}
            for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_PARK"
        ]
        self.assertEqual(parks, [{"PARKED": True, "UNPARKED": False}])

    def test_park_does_not_send_tracking_off(self):
        self._stub_park_properties()
        self.telescope.park(TelescopeSpeed.SPEED_NOT_TRACKING)
        self.assertNotIn("MOUNT_TRACKING", self._sent_property_names())

    def test_park_does_not_write_park_position_when_mount_has_none(self):
        self._stub_park_properties()
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        self.assertNotIn("MOUNT_PARK_POSITION", self._sent_property_names())

    def test_park_syncs_park_position_before_parking_when_supported(self):
        self._stub_park_properties({
            "MOUNT_PARK_POSITION": {"items": [{"name": "HA", "value": 0}, {"name": "DEC", "value": 0}]},
            "MOUNT_PARK": {"items": [{"name": "PARKED", "value": False}]},
        })
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        names = self._sent_property_names()
        self.assertLess(names.index("MOUNT_PARK_POSITION"), names.index("MOUNT_PARK"))

    def test_park_skips_park_position_sync_when_already_parked(self):
        self._stub_park_properties({
            "MOUNT_PARK_POSITION": {"items": [{"name": "HA", "value": 0}, {"name": "DEC", "value": 0}]},
            "MOUNT_PARK": {"items": [{"name": "PARKED", "value": True}]},
        })
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        self.assertNotIn("MOUNT_PARK_POSITION", self._sent_property_names())

    def test_set_speed_sends_on_coordinates_set_as_switch_vector_even_when_not_tracking(self):
        self.telescope.set_speed(TelescopeSpeed.SPEED_NOT_TRACKING)
        coord_set = next(s["newSwitchVector"] for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_ON_COORDINATES_SET")
        items = {i["name"]: i["value"] for i in coord_set["items"]}
        self.assertEqual(items["TRACK"], True)
        tracking = next(s["newSwitchVector"] for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_TRACKING")
        tracking_items = {i["name"]: i["value"] for i in tracking["items"]}
        self.assertEqual(tracking_items, {"ON": False, "OFF": True})

    def test_flat_unparks_before_moving(self):
        self._stub_park_properties()
        self.telescope.flat(TelescopeSpeed.SPEED_NOT_TRACKING)
        names_in_order = self._sent_property_names()
        self.assertIn("MOUNT_PARK", names_in_order)
        self.assertIn("MOUNT_ON_COORDINATES_SET", names_in_order)
        self.assertIn("MOUNT_EQUATORIAL_COORDINATES", names_in_order)
        self.assertLess(
            names_in_order.index("MOUNT_PARK"),
            names_in_order.index("MOUNT_EQUATORIAL_COORDINATES"),
        )
        self.assertLess(
            names_in_order.index("MOUNT_ON_COORDINATES_SET"),
            names_in_order.index("MOUNT_EQUATORIAL_COORDINATES"),
        )

    def test_flat_turns_tracking_off_only_after_slew_completes(self):
        states = iter([{"state": "Ok"}, {"state": "Busy"}, {"state": "Busy"}, {"state": "Ok"}])

        self.mock_client.get_property.side_effect = lambda device, name, timeout=2.0: next(states)
        with patch("crac_server.component.telescope.indigo.telescope.time.sleep"):
            self.telescope.flat(TelescopeSpeed.SPEED_NOT_TRACKING)
        self.assertEqual(list(states), [], "every coordinate state was read")
        last_tracking = [s for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_TRACKING"][-1]
        items = {i["name"]: i["value"] for i in last_tracking["newSwitchVector"]["items"]}
        self.assertEqual(items, {"ON": False, "OFF": True})

    def test_slew_timeout_with_unmoving_coordinates_logs_a_suspected_indigo_stall(self):
        self.mock_client.get_property.side_effect = lambda device, name, timeout=0: {
            "state": "Busy", "items": [{"name": "RA", "value": 1.0}, {"name": "DEC", "value": 2.0}]
        }
        self.mock_client.seconds_since_last_message.return_value = 0.5
        with patch("crac_server.component.telescope.indigo.telescope.time.sleep"), \
             self.assertLogs("crac_server.component.telescope.indigo.telescope", level="WARNING") as logs:
            self.telescope._Telescope__wait_for_slew_completion(0.05)
        self.assertIn("likely an INDIGO-side stall", logs.output[-1])
        self.assertIn("only this device", logs.output[-1])

    def test_slew_timeout_blames_the_whole_bus_when_nothing_at_all_arrived(self):
        self.mock_client.get_property.side_effect = lambda device, name, timeout=0: {
            "state": "Busy", "items": [{"name": "RA", "value": 1.0}, {"name": "DEC", "value": 2.0}]
        }
        self.mock_client.seconds_since_last_message.return_value = 30.0
        with patch("crac_server.component.telescope.indigo.telescope.time.sleep"), \
             self.assertLogs("crac_server.component.telescope.indigo.telescope", level="WARNING") as logs:
            self.telescope._Telescope__wait_for_slew_completion(0.05)
        self.assertIn("the whole bus", logs.output[-1])

    def test_slew_timeout_with_moving_coordinates_keeps_the_generic_error(self):
        ra = {"value": 1.0}

        def get_property(device, name, timeout=0):
            ra["value"] += 0.001
            return {"state": "Busy", "items": [{"name": "RA", "value": ra["value"]}, {"name": "DEC", "value": 2.0}]}

        self.mock_client.get_property.side_effect = get_property
        with patch("crac_server.component.telescope.indigo.telescope.time.sleep"), \
             self.assertLogs("crac_server.component.telescope.indigo.telescope", level="ERROR") as logs:
            self.telescope._Telescope__wait_for_slew_completion(0.05)
        self.assertIn("giving up waiting", logs.output[-1])
