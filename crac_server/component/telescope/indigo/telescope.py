from datetime import datetime
from typing import Any
import time
from astropy.time import Time
from crac_protobuf.telescope_pb2 import (
    EquatorialCoords,
    AltazimutalCoords,
    TelescopeSpeed,
    TelescopeStatus,  # type: ignore
)
from crac_server import config
from crac_server.component.telescope.telescope import Telescope as TelescopeBase
from crac_server.status_log import ErrorCause
import json
import logging
logger = logging.getLogger(__name__)

COORDINATES_AT_REST = ("Ok", "Idle")
READ_WINDOW = 1.0
READ_CHUNK_TIMEOUT = 0.3


class Telescope(TelescopeBase):

    def __init__(self, hostname=None, port=None) -> None:
        """Build the driver without touching the mount.

        No connect_device() here: the operator establishes the connection
        from the INDIGO panel (mount.html/ctrl.html) before crac uses the
        mount, see retrieve(). The configuration is read in the body and not
        in the default arguments, which would run at import time.
        """
        hostname = config.Config.getValue("hostname", "telescope") if hostname is None else hostname
        port = config.Config.getInt("port", "telescope") if port is None else port
        super().__init__(hostname=hostname, port=port)
        self._name = config.Config.getValue("name", "indigo")
        self._park_position_synced = False
        self._uses_raw_socket = True

    def __sync_park_position(self):
        """Align the mount park position to the configured park_alt/park_az.

        Expressed as HA/DEC rather than alt/az because, for a fixed alt/az
        point, those are the only time-invariant equatorial coordinates
        (alt/az = f(HA, dec, lat), so the same HA/dec always lands on the
        same alt/az, unlike RA which has to be recomputed at every instant).
        Synced once, from park() and never eagerly, and only while the mount
        is unparked: the driver refuses the write on a parked one.
        """
        if self._park_position_synced:
            return
        if not self.__mount_exposes_a_park_position():
            return
        if self.__retrieve_status_park():
            return
        obstime = datetime.utcnow()
        aa_coords = AltazimutalCoords(
            alt=config.Config.getFloat("park_alt", "telescope"),
            az=config.Config.getFloat("park_az", "telescope"),
        )
        eq_coords = self._altaz2radec(aa_coords, obstime=obstime)
        lon = config.Config.getValue("lon", "geography")
        lst = Time(obstime).sidereal_time("apparent", longitude=lon)
        ha = (lst.hour - eq_coords.ra) % 24
        if ha > 12:
            ha -= 24
        self._park_position_synced = self.__call(
                    {"newNumberVector":
                        {
                            "device": self._name, "name": "MOUNT_PARK_POSITION", "items":
                            [
                                { "name": "HA", "value": ha},
                                { "name": "DEC", "value": eq_coords.dec}
                            ]
                        }
                    }
                    )

    def __mount_exposes_a_park_position(self) -> bool:
        """True only where the park position is writable, the Mount Simulator.

        On a real mount it lives in the mount and MOUNT_PARK_POSITION does not
        exist at all.
        """
        return bool(self.__property(self.__enumerate(), "MOUNT_PARK_POSITION"))

    def sync(self, started_at: datetime):
        """Not supported on INDIGO: the mount knows where it points.

        Declaring the park position to the mount would overwrite what the
        mount itself holds, and MOUNT_PARK already covers it. The method
        stays only to satisfy the abstract contract.
        """
        logger.warning("[Telescope] SYNC is not supported on INDIGO, nothing was sent to the mount")

    def set_speed(self, speed: TelescopeSpeed):
        """Set tracking, then ask for a slew on the next coordinates.

        MOUNT_ON_COORDINATES_SET is a switch property: sent as a number vector
        the driver ignores it. TRACK is what produces a slew, whatever tracking
        is wanted on arrival.
        """
        tracking_on = speed is not TelescopeSpeed.SPEED_NOT_TRACKING
        self.__call(
                    {"newSwitchVector":
                            {
                                "device": self._name, "name": "MOUNT_TRACKING", "state": "Ok", "items":
                                [
                                    { "name": "ON", "value": tracking_on},
                                    { "name": "OFF", "value": not tracking_on}
                                ]
                            }
                        }
                    )

        self.__call(
                    {"newSwitchVector":
                        {
                            "device": self._name, "name": "MOUNT_ON_COORDINATES_SET", "state": "Ok", "items":
                            [
                                { "name": "SLEW", "value": False},
                                { "name": "TRACK", "value": True},
                                { "name": "SYNC", "value": False}
                            ]
                        }
                    }
                )


    def park(self, speed: TelescopeSpeed):
        """Park the mount natively, sending MOUNT_PARK on its own.

        No preventive unpark: on a real mount (indigo_mount_lx200, e.g. the
        TeenAstro) the driver drops MOUNT_PARK while the mount still reads
        parked/parking/homing, yet echoes PARKED=true back anyway, because
        indigo_property_copy_values runs before that guard. Unparking is
        asynchronous, `parked` stays true for a moment, so an UNPARK sent
        right before a PARK lands in exactly that case. Tracking is not
        touched either: parking already stops it.
        """
        self.__sync_park_position()
        self.__call(
                        {"newSwitchVector":
                            {
                                "device": self._name, "name": "MOUNT_PARK", "state": "Ok", "items":
                                    [
                                        { "name": "PARKED", "value": True},
                                        { "name": "UNPARKED", "value": False}
                                    ]
                            }
                        }
                    )

        self.__wait_for_slew_completion()

    def __retrieve_status_park(self, root: list | None = None) -> bool:
        prop = self.__property(root if root is not None else self.__enumerate(), "MOUNT_PARK")
        if not prop:
            return False
        for park in prop.get("items", []):
            if park.get("name") == "PARKED":
                return bool(park.get("value"))
        return False

    def __unpark(self):
        """Release the mount before a slew.

        A parked mount refuses every movement command
        (indigo_mount_simulator.c: MOUNT_PARK_PARKED_ITEM->sw.value puts
        MOUNT_EQUATORIAL_COORDINATES in ALERT, "Mount is parked"), so it is
        unparked explicitly, as the other drivers do too, see
        ascom_hub._unpark_and_track.
        """
        self.__call(
                        {"newSwitchVector":
                            {
                                "device": self._name, "name": "MOUNT_PARK", "state": "Ok", "items":
                                    [
                                        { "name": "PARKED", "value": False},
                                        { "name": "UNPARKED", "value": True}
                                    ]
                            }
                        }
                    )

    def flat(self, speed: TelescopeSpeed):
        """Move to the configured flat position.

        With tracking off the slew is awaited before switching it off again:
        the simulator turns it back on by itself as soon as a slew ends.
        """
        speed=speed
        self.__unpark()
        self.__move(
                    aa_coords=AltazimutalCoords(
                        alt=config.Config.getFloat("flat_alt", "telescope"),
                        az=config.Config.getFloat("flat_az", "telescope")
                    ),
                speed=speed
                )

        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            self.__wait_for_slew_completion()
            self.__call(
                            {"newSwitchVector":
                                {
                                    "device": self._name, "name": "MOUNT_TRACKING", "state": "Ok", "items":
                                    [
                                        { "name": "ON", "value": False},
                                        { "name": "OFF", "value": True}
                                    ]
                                }
                            }
                        )

    def __wait_for_slew_completion(self, timeout: float = 60.0):
        """Block until MOUNT_EQUATORIAL_COORDINATES leaves the Busy state.

        Busy is awaited first, on a shorter deadline: right after a command the
        cache can still hold the previous "Ok", the INDIGO broadcast not having
        arrived yet.
        """
        deadline = time.monotonic() + timeout

        busy_deadline = min(deadline, time.monotonic() + 5.0)
        while time.monotonic() < busy_deadline:
            coords = self.__property(self.__enumerate(), "MOUNT_EQUATORIAL_COORDINATES")
            if coords and coords.get("state") == "Busy":
                break
            time.sleep(0.1)

        while time.monotonic() < deadline:
            coords = self.__property(self.__enumerate(), "MOUNT_EQUATORIAL_COORDINATES")
            if coords and coords.get("state") != "Busy":
                return
            time.sleep(0.3)
        logger.error(f"[Telescope] Slew did not complete within {timeout}s, giving up waiting")

    def retrieve(self) -> tuple:
        """Read the mount state.

        One enumeration per cycle answers everything: coordinates, tracking
        and park state are read from the same answer, so the mount is asked
        once and the connection can be closed right after.

        Every coordinate here is read, never written: the site lives in the
        mount and is the reference the mount converts RA/DEC to ALT/AZ
        against, so crac takes MOUNT_HORIZONTAL_COORDINATES as it comes.

        A device the operator has not connected from the INDIGO panel reports
        no CONNECTION at all, and crac declares it lost instead of connecting
        it itself.
        """
        root = self.__enumerate()
        if not self.__device_is_connected(root):
            return (None, None, TelescopeSpeed.SPEED_ERROR, TelescopeStatus.LOST)

        eq_coords = self.__retrieve_eq_coords(root)
        logger.debug(f"data received from indigo: {eq_coords}")
        speed = self.__retrieve_speed(root)
        logger.debug(f"data received from indigo: {speed}")
        aa_coords = self.__retrieve_aa_coords(root)
        logger.debug(f"data received from indigo: {aa_coords}")
        status = self._retrieve_status(aa_coords, root)
        logger.debug(f"data received from indigo: {status}")

        return (eq_coords, aa_coords, speed, status)

    def _retrieve_status(self, aa_coords: AltazimutalCoords, root: list | None = None) -> TelescopeStatus:
        if not self._polling:
            return TelescopeStatus.DISCONNECTED
        elif self.__retrieve_status_park(root):
            return TelescopeStatus.PARKED
        elif self.__within_flat_alt_range(aa_coords.alt) and self.__within_flat_az_range(aa_coords.az):
            return TelescopeStatus.FLATTER
        elif aa_coords.alt <= config.Config.getFloat("max_secure_alt", "telescope"):
            return TelescopeStatus.SECURE
        else:
            if config.Config.getInt("azNE", "azimut") > aa_coords.az:
                return TelescopeStatus.NORTHEAST
            elif aa_coords.az > config.Config.getInt("azNW", "azimut"):
                return TelescopeStatus.NORTHWEST
            elif config.Config.getInt("azSW", "azimut") > aa_coords.az > 180:
                return TelescopeStatus.SOUTHWEST
            elif 180 >= aa_coords.az > config.Config.getInt("azSE", "azimut"):
                return TelescopeStatus.SOUTHEAST
            elif config.Config.getInt("azSW", "azimut") < aa_coords.az <= config.Config.getInt("azNW", "azimut"):
                return TelescopeStatus.WEST
            elif config.Config.getInt("azNE", "azimut") <= aa_coords.az <= config.Config.getInt("azSE", "azimut"):
                return TelescopeStatus.EAST

    def __move(self, aa_coords: AltazimutalCoords, speed=TelescopeSpeed.SPEED_TRACKING):
        """Slew to aa_coords, converted to RA/DEC against [geography].

        set_speed() goes out here instead of through the queue: the driver
        reads MOUNT_ON_COORDINATES_SET at the very moment the coordinates
        arrive, not at the next polling cycle.
        """
        eq_coords = self._altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow()) if isinstance(aa_coords, (AltazimutalCoords)) else aa_coords
        logger.debug("aa_coords: %s", aa_coords)
        logger.debug("eq_coords: %s", eq_coords)
        self.set_speed(speed)
        self.__call(
                    {"newNumberVector":
                        {
                            "device": self._name, "name": "MOUNT_EQUATORIAL_COORDINATES", "state": "Ok", "items":
                            [
                                { "name": "DEC", "value": eq_coords.dec},
                                { "name": "RA", "value": eq_coords.ra}
                            ]
                        }
                    }
                    )

    def __retrieve_speed(self, root: list) -> TelescopeSpeed:
        """Map the state of the mount to a TelescopeSpeed.

        The state of the coordinates says whether a slew is under way, and
        MOUNT_TRACKING tells a resting mount from a tracking one: at rest
        indigo_mount_simulator.c reports "Ok" and indigo_mount_lx200 "Idle",
        and neither is a fault.
        """
        tracking = self.__property(root, "MOUNT_TRACKING")
        coords = self.__property(root, "MOUNT_EQUATORIAL_COORDINATES")

        status_mount_track = None
        if tracking:
            for track in tracking.get("items", []):
                if track.get("name") == "ON":
                    status_mount_track = "ON" if track.get("value") else "OFF"

        status_mount_speed = coords.get("state") if coords else None

        if status_mount_speed in COORDINATES_AT_REST and status_mount_track == "ON":
            self._speed_log.record(TelescopeSpeed.SPEED_TRACKING)
            return TelescopeSpeed.SPEED_TRACKING
        if status_mount_speed in COORDINATES_AT_REST and status_mount_track == "OFF":
            self._speed_log.record(TelescopeSpeed.SPEED_NOT_TRACKING)
            return TelescopeSpeed.SPEED_NOT_TRACKING
        if status_mount_speed == "Busy":
            self._speed_log.record(TelescopeSpeed.SPEED_SLEWING)
            return TelescopeSpeed.SPEED_SLEWING

        self._speed_log.record(
            TelescopeSpeed.SPEED_ERROR,
            ErrorCause.DEVICE_UNREACHABLE if not coords or not tracking else ErrorCause.STATE_NOT_RECOGNIZED,
            detail=f"coordinates: {status_mount_speed}, tracking: {status_mount_track}",
        )
        return TelescopeSpeed.SPEED_ERROR

    def __retrieve_eq_coords(self, root: list) -> EquatorialCoords:
        prop = self.__property(root, "MOUNT_EQUATORIAL_COORDINATES")
        ra, dec = None, None
        if prop:
            for coord in prop.get("items", []):
                if coord.get("name") == "RA":
                    ra = round(float(coord["value"]), 5)
                elif coord.get("name") == "DEC":
                    dec = round(float(coord["value"]), 5)

        if ra is not None and dec is not None:
            return EquatorialCoords(ra=ra, dec=dec)
        raise Exception(f"RA or Dec not present. RA: {ra}, DEC: {dec}")

    def __retrieve_aa_coords(self, root: list) -> AltazimutalCoords:
        prop = self.__property(root, "MOUNT_HORIZONTAL_COORDINATES")
        alt, az = None, None
        if prop:
            for coord in prop.get("items", []):
                if coord.get("name") == "ALT":
                    alt = round(float(coord["value"]), 5)
                elif coord.get("name") == "AZ":
                    az = round(float(coord["value"]), 5)

        if alt is not None and az is not None:
            return AltazimutalCoords(alt=alt, az=az)
        raise Exception(f"ALT or AZ not present. ALT: {alt}, AZ: {az}")

    def __call(self, script) -> bool:
        """Write one script on the connection of this cycle.

        The polling loop opens that connection before every cycle and closes
        it after (_uses_raw_socket), so nothing of crac stays subscribed to
        the bus between one read and the next.
        """
        if getattr(self, "s", None) is None:
            return False
        try:
            self.s.sendall(json.dumps(script).encode("utf-8") + b"\n")
            return True
        except OSError as e:
            logger.error(f"[Telescope] Send error: {e}")
            return False

    def __enumerate(self) -> list:
        """Ask the device for its properties and return the vectors it answers.

        The trailing newline is what makes INDIGO parse the request: without
        it the enumeration is never answered on the same connection.
        """
        if not self.__call({"getProperties": {"version": 512, "device": self._name}}):
            return []
        decoder = json.JSONDecoder()
        deadline = time.monotonic() + READ_WINDOW
        self.s.settimeout(READ_CHUNK_TIMEOUT)
        buffer, vectors = "", []
        while time.monotonic() < deadline:
            try:
                data = self.s.recv(65536)
            except OSError:
                break
            if not data:
                break
            buffer += data.decode("utf-8", errors="ignore")
            while True:
                buffer = buffer.lstrip()
                if not buffer:
                    break
                try:
                    message, index = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    break
                buffer = buffer[index:]
                vectors.append(message)
        return vectors

    def __device_is_connected(self, root: list) -> bool:
        """Whether INDIGO reports the device as connected, without ever
        connecting it: on the telescope that is the operator's move, from the
        INDIGO panel, and never crac's."""
        prop = self.__property(root, "CONNECTION")
        if not prop:
            return False
        for item in prop.get("items", []):
            if item.get("name") == "CONNECTED":
                return bool(item.get("value"))
        return False

    @staticmethod
    def __property(root: list, name: str) -> dict | None:
        """The last vector named `name` in an answer, whatever its type.

        Matching on the name and not on defNumberVector/defSwitchVector keeps
        one lookup for every property, and an update that arrives inside the
        same read window wins over the definition that preceded it.
        """
        found = None
        for message in root:
            for key, vector in message.items():
                if key[:3] in ("def", "set") and vector.get("name") == name:
                    found = vector
        return found
