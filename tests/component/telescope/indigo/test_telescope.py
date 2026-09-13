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
        self.sent_scripts = []
        self.mock_client.send.side_effect = lambda script: self.sent_scripts.append(script) or True
        self.telescope = Telescope(hostname="host", port=1)

    def _stub_properties(self, props: dict):
        def get_property(device, name, timeout=2.0):
            return props.get(name)
        self.mock_client.get_property.side_effect = get_property

    def _sent_property_names(self):
        """Names of the properties sent to INDIGO, in order.

        Each script is a single-entry mapping of vector type to its body,
        e.g. {"newSwitchVector": {"name": "MOUNT_PARK", ...}}.
        """
        return [vector["name"] for script in self.sent_scripts for vector in script.values()]

    def test_init_does_not_force_connection_and_skips_raw_socket_polling(self):
        """The operator connects the mount from the INDIGO panel, not crac."""
        self.mock_client.connect_device.assert_not_called()
        self.assertFalse(self.telescope._uses_raw_socket)

    def test_geographic_coordinates_are_never_sent_to_the_mount(self):
        """The observatory site is read from the mount, never written to it."""
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.assertNotIn("GEOGRAPHIC_COORDINATES", self._sent_property_names())

    def test_retrieve_reconnects_device_on_every_cycle(self):
        """A client reconnection empties the property cache, so the device is
        re-connected on every cycle or it stays stuck forever."""
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.telescope.retrieve()
        self.assertEqual(self.mock_client.connect_device.call_count, 2)

    def test_retrieve_refuses_when_device_not_connected_on_indigo(self):
        """Until the operator connects the mount on INDIGO the telescope is
        reported as LOST, never as connected."""
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
        """indigo_mount_simulator.c only ever uses "Ok"/"Busy"/"Alert" for
        MOUNT_EQUATORIAL_COORDINATES: idle with tracking off still reads
        "Ok", so the tracking property alone tells the two apart."""
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
        sent = self.sent_scripts[-1]
        self.assertEqual(sent["newSwitchVector"]["name"], "MOUNT_PARK")
        items = {i["name"]: i["value"] for i in sent["newSwitchVector"]["items"]}
        self.assertEqual(items, {"PARKED": True, "UNPARKED": False})

    def _stub_park_properties(self, extra: dict | None = None):
        """Stub a park slew that completes at once: Busy on the first read,
        meaning the command was taken in charge, then Ok, so that
        __wait_for_slew_completion returns instead of hitting its timeout.
        """
        states = iter([{"state": "Busy"}, {"state": "Ok"}])
        props = dict(extra or {})

        def get_property(device, name, timeout=2.0):
            if name == "MOUNT_EQUATORIAL_COORDINATES":
                return next(states, {"state": "Ok"})
            return props.get(name)

        self.mock_client.get_property.side_effect = get_property

    def test_park_does_not_unpark_first(self):
        """indigo_mount_lx200 (TeenAstro) drops MOUNT_PARK while the mount
        still reads parked/parking/homing, yet echoes PARKED=true anyway,
        since indigo_property_copy_values runs before that guard. Unparking
        is asynchronous, so an UNPARK sent right before a PARK lands in
        exactly that case: park goes out on its own.
        """
        self._stub_park_properties()
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        parks = [
            {i["name"]: i["value"] for i in s["newSwitchVector"]["items"]}
            for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_PARK"
        ]
        self.assertEqual(parks, [{"PARKED": True, "UNPARKED": False}])

    def test_park_does_not_send_tracking_off(self):
        """Parking already stops tracking, on the simulator and on a real
        mount alike, and a MOUNT_TRACKING command reaching a parked mount is
        refused with the property in Alert, or hits the hardware mid-park.
        """
        self._stub_park_properties()
        self.telescope.park(TelescopeSpeed.SPEED_NOT_TRACKING)
        self.assertNotIn("MOUNT_TRACKING", self._sent_property_names())

    def test_park_does_not_write_park_position_when_mount_has_none(self):
        """On a real mount MOUNT_PARK_POSITION does not exist: the park
        position lives in the mount, and writing it would be pure noise."""
        self._stub_park_properties()
        self.telescope.park(TelescopeSpeed.SPEED_TRACKING)
        self.assertNotIn("MOUNT_PARK_POSITION", self._sent_property_names())

    def test_park_syncs_park_position_before_parking_when_supported(self):
        """The Mount Simulator exposes MOUNT_PARK_POSITION and starts from a
        park position of its own: it is aligned to the configured
        park_alt/park_az before parking, and only while the mount is
        unparked, since the driver refuses the write on a parked one.
        """
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
        """MOUNT_ON_COORDINATES_SET is a switch property, not a number one:
        sent as a newNumberVector the driver ignores it and the slew of
        MOUNT_EQUATORIAL_COORDINATES never fires. It goes out for
        SPEED_NOT_TRACKING too, the real case of flat() in this
        configuration: indigo_mount_simulator.c implements only the TRACK and
        SYNC branches for movement, so TRACK is what produces a slew,
        whatever tracking is wanted on arrival, which MOUNT_TRACKING governs
        on its own.
        """
        self.telescope.set_speed(TelescopeSpeed.SPEED_NOT_TRACKING)
        coord_set = next(s["newSwitchVector"] for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_ON_COORDINATES_SET")
        items = {i["name"]: i["value"] for i in coord_set["items"]}
        self.assertEqual(items["TRACK"], True)
        tracking = next(s["newSwitchVector"] for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_TRACKING")
        tracking_items = {i["name"]: i["value"] for i in tracking["items"]}
        self.assertEqual(tracking_items, {"ON": False, "OFF": True})

    def test_flat_unparks_before_moving(self):
        self._stub_properties({"MOUNT_EQUATORIAL_COORDINATES": {"state": "Ok"}})
        self.telescope.flat(TelescopeSpeed.SPEED_NOT_TRACKING)
        names_in_order = self._sent_property_names()
        self.assertIn("MOUNT_PARK", names_in_order)
        self.assertIn("MOUNT_ON_COORDINATES_SET", names_in_order)
        self.assertIn("MOUNT_EQUATORIAL_COORDINATES", names_in_order)
        # the driver reads MOUNT_ON_COORDINATES_SET.TRACK at the very moment
        # it receives the new coordinates, so both have to reach it first
        self.assertLess(
            names_in_order.index("MOUNT_PARK"),
            names_in_order.index("MOUNT_EQUATORIAL_COORDINATES"),
        )
        self.assertLess(
            names_in_order.index("MOUNT_ON_COORDINATES_SET"),
            names_in_order.index("MOUNT_EQUATORIAL_COORDINATES"),
        )

    def test_flat_turns_tracking_off_only_after_slew_completes(self):
        """indigo_mount_simulator.c turns MOUNT_TRACKING back on by itself as
        soon as a slew ends, so tracking is switched off again only once the
        state leaves Busy. The leading "Ok" stands for the cache not yet
        updated right after the coordinates go out, which is why Busy is
        awaited before waiting for Ok.
        """
        states = iter([{"state": "Ok"}, {"state": "Busy"}, {"state": "Busy"}, {"state": "Ok"}])
        self.mock_client.get_property.side_effect = lambda device, name, timeout=2.0: next(states)
        with patch("crac_server.component.telescope.indigo.telescope.time.sleep"):
            self.telescope.flat(TelescopeSpeed.SPEED_NOT_TRACKING)
        self.assertEqual(self.mock_client.get_property.call_count, 4)
        last_tracking = [s for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_TRACKING"][-1]
        items = {i["name"]: i["value"] for i in last_tracking["newSwitchVector"]["items"]}
        self.assertEqual(items, {"ON": False, "OFF": True})
