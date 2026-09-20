from datetime import datetime
from typing import Any
import threading
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
from crac_server.component.client.indigo import get_indigo_client
from crac_server.status_log import ErrorCause
import logging
logger = logging.getLogger(__name__)

COORDINATES_AT_REST = ("Ok", "Idle")
# indigo_mount_lx200's position timer publishes every 0.5-1s while the
# device is connected, unconditionally (indigo_update_property() in this
# INDIGO version writes to every client regardless of whether the value
# changed). A single slow client's write is capped at 5s by
# indigo_server_tcp.c's own SO_SNDTIMEO, and INDIGO's global bus lock means
# that stall briefly freezes every other client too.
INDIGO_STALL_SECONDS = 5.0
# A stall like that is benign and self-resolving, not a dead connection, so
# the watchdog sits well above it and only fires on silence INDIGO itself
# would not call normal.
STALE_CONNECTION_SECONDS = 15.0


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
        self._client = get_indigo_client(hostname, port)
        self._park_position_synced = False
        self._uses_raw_socket = False

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
        return bool(self._client.get_property(self._name, "MOUNT_PARK_POSITION", timeout=0))

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

    def __retrieve_status_park(self) -> bool:
        prop = self._client.get_property(self._name, "MOUNT_PARK", timeout=0)
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
            coords = self._client.get_property(self._name, "MOUNT_EQUATORIAL_COORDINATES", timeout=0)
            if coords and coords.get("state") == "Busy":
                break
            time.sleep(0.1)

        baseline = self.__coords_values(coords) if coords else None
        while time.monotonic() < deadline:
            coords = self._client.get_property(self._name, "MOUNT_EQUATORIAL_COORDINATES", timeout=0)
            if coords and coords.get("state") != "Busy":
                return
            time.sleep(0.3)

        if baseline is not None and coords and self.__coords_values(coords) == baseline:
            self.__log_suspected_indigo_stall(timeout)
        else:
            logger.error(f"[Telescope] Slew did not complete within {timeout}s, giving up waiting")

    def __log_suspected_indigo_stall(self, timeout: float):
        """RA/DEC never moved for the whole wait: not a real hang of the
        mount, which would still show through a state change even stuck in
        Alert, but INDIGO's own driver thread stalling under its global bus
        lock while writing to some other slow client (bus_mutex/json_mutex,
        capped at 5s per client by SO_SNDTIMEO - see
        analisi-blocco-montatura-indigo-2026-09-17.md).
        """
        quiet = self._client.seconds_since_last_message()
        where = "the whole bus" if quiet > INDIGO_STALL_SECONDS else "only this device"
        logger.warning(
            f"[Telescope] Slew did not complete within {timeout}s and RA/DEC never moved - "
            f"likely an INDIGO-side stall, not a real mount hang ({where} silent for {quiet:.0f}s). "
            'Check `ss -tn "sport = :7624"` on the INDIGO host for a client with a growing send queue.'
        )

    @staticmethod
    def __coords_values(coords: dict) -> tuple:
        values = {item.get("name"): item.get("value") for item in coords.get("items", [])}
        return (values.get("RA"), values.get("DEC"))

    def retrieve(self) -> tuple:
        """Read the mount state.

        Every coordinate here is read, never written: the site lives in the
        mount and is the reference the mount converts RA/DEC to ALT/AZ
        against, so crac takes MOUNT_HORIZONTAL_COORDINATES as it comes.

        connect_device() belongs in every cycle and not only in __init__: a
        client reconnection empties the cache, and its result reports that the
        device state was lost, so one-shot syncs have to be repeated.
        """
        if not self._client.is_device_connected(self._name):
            return (None, None, TelescopeSpeed.SPEED_ERROR, TelescopeStatus.LOST)

        if self._client.seconds_since_last_message(self._name) > STALE_CONNECTION_SECONDS:
            bus_quiet = self._client.seconds_since_last_message()
            if bus_quiet > STALE_CONNECTION_SECONDS:
                # The whole shared socket looks dead, not just this device -
                # worth reconnecting, and every other consumer of this same
                # client (e.g. the mirror cover) is equally silent already,
                # so clearing its cache costs them nothing they still had.
                # No need to also stop polling: the reconnect already leaves
                # the client healthy, and the next cycle picks up from there.
                logger.warning(
                    f"[Telescope] Nothing at all received on the INDIGO connection for over "
                    f"{bus_quiet:.0f}s - treating the shared connection as dead and reconnecting it"
                )
                self._client.reconnect()
            else:
                # Only this device has gone quiet while the rest of the bus
                # is fine - reconnecting the shared client wouldn't fix an
                # INDIGO-side problem specific to this device, and would
                # needlessly flush the cache of every other consumer of the
                # same client (the mirror cover, notably).
                logger.warning(
                    f"[Telescope] Nothing received about {self._name} for over "
                    f"{STALE_CONNECTION_SECONDS:.0f}s while the rest of the INDIGO bus is still "
                    "talking - treating the connection as dead: stopping polling, the operator "
                    "has to reconnect from crac-cloud"
                )
                # Not a direct self._polling = False: retrieve() runs on self.t,
                # and polling_end() calls self.t.join() - a thread cannot join
                # itself. Running polling_end() from a throwaway thread reuses
                # its existing stop-and-join instead of a second, unsynchronized
                # way to flip the same flag, which a concurrent polling_start()
                # could otherwise race into starting a second worker thread.
                threading.Thread(target=self.polling_end, daemon=True).start()
            return (None, None, TelescopeSpeed.SPEED_ERROR, TelescopeStatus.DISCONNECTED)

        if self._client.connect_device(self._name):
            self._park_position_synced = False
        eq_coords = self.__retrieve_eq_coords()
        logger.debug(f"data received from cache: {eq_coords}")
        speed = self.__retrieve_speed()
        logger.debug(f"data received from cache: {speed}")
        aa_coords = self.__retrieve_aa_coords()
        logger.debug(f"data received from cache: {aa_coords}")
        status = self._retrieve_status(aa_coords)
        logger.debug(f"data received from cache: {status}")

        return (eq_coords, aa_coords, speed, status)

    def _retrieve_status(self, aa_coords: AltazimutalCoords) -> TelescopeStatus:
        if not self._polling:
            return TelescopeStatus.DISCONNECTED
        elif self.__retrieve_status_park():
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

    def __retrieve_speed(self) -> TelescopeSpeed:
        """Map the state of the mount to a TelescopeSpeed.

        The state of the coordinates says whether a slew is under way, and
        MOUNT_TRACKING tells a resting mount from a tracking one: at rest
        indigo_mount_simulator.c reports "Ok" and indigo_mount_lx200 "Idle",
        and neither is a fault.
        """
        tracking = self._client.get_property(self._name, "MOUNT_TRACKING", timeout=0)
        coords = self._client.get_property(self._name, "MOUNT_EQUATORIAL_COORDINATES", timeout=0)

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

    def __retrieve_eq_coords(self) -> EquatorialCoords:
        prop = self._client.get_property(self._name, "MOUNT_EQUATORIAL_COORDINATES")
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

    def __retrieve_aa_coords(self) -> AltazimutalCoords:
        prop = self._client.get_property(self._name, "MOUNT_HORIZONTAL_COORDINATES")
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
        return self._client.send(script)
