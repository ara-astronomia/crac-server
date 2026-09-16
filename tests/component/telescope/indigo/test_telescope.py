import itertools
import json
import unittest
from unittest.mock import MagicMock, patch

from crac_protobuf.telescope_pb2 import AltazimutalCoords, TelescopeSpeed, TelescopeStatus
from crac_server.component.telescope.indigo.telescope import Telescope


CONNECTED = {"items": [{"name": "CONNECTED", "value": True}]}


class TestIndigoTelescope(unittest.TestCase):

    def setUp(self):
        self.telescope = Telescope(hostname="host", port=1)
        self.sent_scripts = []
        self._properties = {}
        self._coordinate_states = None
        self._answered = False
        socket = MagicMock()
        socket.sendall.side_effect = lambda payload: self.sent_scripts.append(json.loads(payload))
        socket.recv.side_effect = self._answer
        self.telescope.s = socket
        sleep_patcher = patch("crac_server.component.telescope.indigo.telescope.time.sleep")
        self.addCleanup(sleep_patcher.stop)
        sleep_patcher.start()

    def _answer(self, _size):
        """INDIGO answers an enumeration with the def vectors of the device,
        and the read ends on the next recv, where a real socket times out."""
        if self._answered:
            self._answered = False
            raise OSError("timed out")
        self._answered = True
        return "".join(json.dumps(vector) for vector in self._vectors()).encode("utf-8")

    def _vectors(self):
        properties = dict(self._properties)
        if self._coordinate_states is not None:
            coordinates = dict(properties.get("MOUNT_EQUATORIAL_COORDINATES", {"items": []}))
            coordinates.update(next(self._coordinate_states))
            properties["MOUNT_EQUATORIAL_COORDINATES"] = coordinates
        return [
            {"defNumberVector": {
                "device": self.telescope._name,
                "name": name,
                "state": prop.get("state", "Ok"),
                "items": prop.get("items", []),
            }}
            for name, prop in properties.items()
        ]

    def _stub_properties(self, props: dict, connected: bool = True):
        self._properties = dict(props)
        if connected:
            self._properties.setdefault("CONNECTION", CONNECTED)

    def _stub_park_properties(self, extra: dict | None = None):
        """Stub a park slew that completes at once: Busy, then Ok."""
        self._stub_properties(dict(extra or {}))
        self._coordinate_states = itertools.cycle([{"state": "Busy"}, {"state": "Ok"}])

    def _sent_property_names(self):
        """Names of the properties written to the mount, in order."""
        return [
            vector["name"]
            for script in self.sent_scripts
            for key, vector in script.items()
            if key.startswith("new")
        ]

    def _enumerations(self):
        return [script for script in self.sent_scripts if "getProperties" in script]

    def test_init_neither_connects_the_device_nor_talks_to_indigo(self):
        self.assertEqual(self.sent_scripts, [])
        self.assertTrue(self.telescope._uses_raw_socket)

    def test_one_enumeration_answers_the_whole_cycle(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.assertEqual(len(self.sent_scripts), 1)
        self.assertEqual(self.sent_scripts[0]["getProperties"]["device"], self.telescope._name)

    def test_every_cycle_asks_the_device_again(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.telescope.retrieve()
        self.assertEqual(len(self._enumerations()), 2)

    def test_a_mount_at_rest_on_idle_coordinates_is_not_an_error(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Idle", "items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
            "MOUNT_TRACKING": {"items": [{"name": "ON", "value": False}]},
        })
        _, _, speed, _ = self.telescope.retrieve()
        self.assertEqual(speed, TelescopeSpeed.SPEED_NOT_TRACKING)

    def test_geographic_coordinates_are_never_sent_to_the_mount(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"items": [{"name": "RA", "value": 1}, {"name": "DEC", "value": 2}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 1}, {"name": "AZ", "value": 2}]},
        })
        self.telescope.retrieve()
        self.assertNotIn("GEOGRAPHIC_COORDINATES", self._sent_property_names())

    def test_retrieve_refuses_when_device_not_connected_on_indigo(self):
        self._stub_properties({}, connected=False)
        eq_coords, aa_coords, speed, status = self.telescope.retrieve()
        self.assertIsNone(eq_coords)
        self.assertIsNone(aa_coords)
        self.assertEqual(speed, TelescopeSpeed.SPEED_ERROR)
        self.assertEqual(status, TelescopeStatus.LOST)
        self.assertEqual(self._sent_property_names(), [])

    def test_retrieve_reads_coordinates_and_speed_from_the_answer(self):
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

    def test_a_slewing_mount_reports_slewing(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Busy", "items": [{"name": "RA", "value": 5.0}, {"name": "DEC", "value": 10.0}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 20.0}, {"name": "AZ", "value": 30.0}]},
            "MOUNT_TRACKING": {"items": [{"name": "ON", "value": True}]},
        })
        _, _, speed, _ = self.telescope.retrieve()
        self.assertEqual(speed, TelescopeSpeed.SPEED_SLEWING)

    def test_coordinates_in_alert_are_a_speed_error(self):
        self._stub_properties({
            "MOUNT_EQUATORIAL_COORDINATES": {"state": "Alert", "items": [{"name": "RA", "value": 5.0}, {"name": "DEC", "value": 10.0}]},
            "MOUNT_HORIZONTAL_COORDINATES": {"items": [{"name": "ALT", "value": 20.0}, {"name": "AZ", "value": 30.0}]},
            "MOUNT_TRACKING": {"items": [{"name": "ON", "value": True}]},
        })
        _, _, speed, _ = self.telescope.retrieve()
        self.assertEqual(speed, TelescopeSpeed.SPEED_ERROR)

    def test_retrieve_raises_when_coordinates_are_missing_from_the_answer(self):
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
        parked = [s for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_PARK"][-1]
        items = {i["name"]: i["value"] for i in parked["newSwitchVector"]["items"]}
        self.assertEqual(items, {"PARKED": True, "UNPARKED": False})

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
        self._stub_park_properties()
        self.telescope.flat(TelescopeSpeed.SPEED_NOT_TRACKING)
        names = self._sent_property_names()
        last_tracking = [s for s in self.sent_scripts if s.get("newSwitchVector", {}).get("name") == "MOUNT_TRACKING"][-1]
        items = {i["name"]: i["value"] for i in last_tracking["newSwitchVector"]["items"]}
        self.assertEqual(items, {"ON": False, "OFF": True})
        self.assertGreater(
            len(names) - 1 - names[::-1].index("MOUNT_TRACKING"),
            names.index("MOUNT_EQUATORIAL_COORDINATES"),
        )
