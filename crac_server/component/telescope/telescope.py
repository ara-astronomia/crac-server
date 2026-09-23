import logging
from abc import ABC, abstractmethod
from astropy import units as u
from astropy.coordinates import (
    EarthLocation,
    AltAz,
    SkyCoord
)
from astropy.time import Time
from collections import deque
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,  # type: ignore
    AltazimutalCoords,  # type: ignore
    EquatorialCoords,  # type: ignore
    TelescopeSpeed,  # type: ignore
)
from crac_server import config
from crac_server.status_log import ErrorCause, StatusLogger
from datetime import datetime
from threading import Lock, Thread
from time import sleep
from typing import NamedTuple, Optional


logger = logging.getLogger(__name__)

ERROR_CAUSE_BY_STATUS = {
    TelescopeStatus.LOST: ErrorCause.DEVICE_UNREACHABLE,
    TelescopeStatus.ERROR: ErrorCause.UNEXPECTED_FAILURE,
}


class TelescopeReading(NamedTuple):
    """What a polling cycle reads from the mount, named by field. Coords are
    None when the mount is unreachable."""
    eq_coords: Optional[EquatorialCoords]
    aa_coords: Optional[AltazimutalCoords]
    speed: TelescopeSpeed
    status: TelescopeStatus


class Telescope(ABC):

    def __init__(self) -> None:
        self._polling = False
        self._jobs = deque()
        self._jobs_lock = Lock()
        self._has_tracking_off_capability = config.Config.getBoolean("tracking_off", "telescope")
        self._flat_coordinate = AltazimutalCoords(alt=config.Config.getFloat("flat_alt", "telescope"), az=config.Config.getFloat("flat_az", "telescope"))
        self._status_log = StatusLogger(logger, "Telescope", TelescopeStatus)
        self._speed_log = StatusLogger(logger, "Telescope speed", TelescopeSpeed)
        self._reset()

    @property
    def status(self) -> TelescopeStatus:
        return self._status

    @status.setter
    def status(self, value: TelescopeStatus) -> None:
        """The status is assigned from several points of the polling loop and
        from whatever retrieve() returns, so the transition is caught here
        instead of at each assignment."""
        self._status_log.record(value, ERROR_CAUSE_BY_STATUS.get(value))
        self._status = value

    @abstractmethod
    def set_speed(self, speed: TelescopeSpeed):
        """ Set the speed of the Telescope """

    @abstractmethod
    def park(self, speed: TelescopeSpeed):
        """ Move the Telescope in the park position """

    @abstractmethod
    def flat(self, speed: TelescopeSpeed):
        """ Move the Telescope in the flat position """

    @abstractmethod
    def retrieve(self) -> TelescopeReading:
        """ Retrieve coordinate and speed from the Telescope """
    
    def polling_start(self):
        if not self._polling:
            logger.info("[Telescope] polling started")
            self._polling = True
            self.t = Thread(target=self.__read)
            self.t.start()
    
    def polling_end(self):
        if self._polling:
            logger.info("[Telescope] polling stopped")
            self._polling = False
            self.t.join()
    
    def _enqueue(self, **job):
        """Queue a command for the polling loop, and log it.
        Deduplicated on the full job under a lock: queue_park() can run
        from another thread than the one handling gRPC requests."""
        with self._jobs_lock:
            if job in self._jobs:
                return
            logger.info(f"[Telescope] {job['action'].__name__} queued, {len(self._jobs) + 1} waiting")
            self._jobs.append(job)

    def queue_set_speed(self, speed: TelescopeSpeed):
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING and not self.has_tracking_off_capability:
            speed = TelescopeSpeed.SPEED_TRACKING
        self._enqueue(action=self.set_speed, speed=speed)
    
    def queue_park(self):
        # Park ignora sempre la luce flat: un mount nativamente parcheggiato
        # rifiuta comunque qualunque cambio di tracking (vedi indigo driver),
        # quindi tenere il tracking acceso in park non è nemmeno ottenibile.
        speed = TelescopeSpeed.SPEED_NOT_TRACKING if self.has_tracking_off_capability else TelescopeSpeed.SPEED_TRACKING
        self._enqueue(action=self.park, speed=speed)

    def queue_flat(self, keep_tracking: bool = False):
        speed = TelescopeSpeed.SPEED_TRACKING if keep_tracking or not self.has_tracking_off_capability else TelescopeSpeed.SPEED_NOT_TRACKING
        self._enqueue(action=self.flat, speed=speed)
    
    @property
    def has_tracking_off_capability(self):
        return self._has_tracking_off_capability
    
    @property
    def polling(self):
        return self._polling

    def is_below_curtains_area(self, alt: float) -> bool:
        return alt <= config.Config.getFloat("max_secure_alt", "telescope")

    def is_above_curtains_area(self, alt: float, max_est: int, max_west: int) -> bool:
        return alt >= max_est and alt >= max_west

    def is_within_curtains_area(self) -> bool:
        return self.status in (
            TelescopeStatus.EAST,
            TelescopeStatus.WEST
        )

    def __read(self):
        """ Polling the Telescope for coordinate and speed.
            Queued actions like move it are dequeued and worked here. """

        while self._polling:
            try:
                if len(self._jobs) > 0:
                    logger.debug(f"there are {len(self._jobs)} jobs: {self._jobs}")
                    job = self._jobs.popleft()
                    logger.info("Running job %s on the telescope", job['action'].__name__)
                    args = {key: val for key ,val in job.items() if key != "action"}
                    job['action'](**args)

                self.eq_coords, self.aa_coords, self.speed, self.status = self.retrieve()
            except:
                logger.error("Error in completing job", exc_info=1)
                self.status = TelescopeStatus.ERROR
                continue
            finally:
                sleep(config.Config.getFloat("polling_interval", "telescope"))
        else:
            self._reset()

    def _reset(self):
        self._status_log.forget()
        self._speed_log.forget()
        self.status = TelescopeStatus.DISCONNECTED
        self.eq_coords: EquatorialCoords = None
        self.aa_coords: AltazimutalCoords = None
        self.speed: TelescopeSpeed = TelescopeSpeed.SPEED_ERROR

    def _retrieve_aa_coords(self, eq_coords):
        if eq_coords:
            aa_coords = self._radec2altaz(eq_coords, obstime=datetime.utcnow()) if eq_coords else None
            return aa_coords

    def _retrieve_status(self, aa_coords: AltazimutalCoords) -> TelescopeStatus:
        if not self._polling:
            return TelescopeStatus.DISCONNECTED
        elif self.__within_park_alt_range(aa_coords.alt) and self.__within_park_az_range(aa_coords.az):
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

    def __within_flat_alt_range(self, alt: float):
        return self.__within_range(alt, config.Config.getFloat("flat_alt", "telescope"))

    def __within_park_alt_range(self, alt: float):
        return self.__within_range(alt, config.Config.getFloat("park_alt", "telescope"))

    def __within_flat_az_range(self, az: float):
        return self.__within_range(az, config.Config.getFloat("flat_az", "telescope"))

    def __within_park_az_range(self, az: float):
        return self.__within_range(az, config.Config.getFloat("park_az", "telescope"))

    def __within_range(self, coord: float, check: float):
        return coord - 2 <= check <= coord + 2
    
    def _radec2altaz(self, eq_coords: EquatorialCoords, obstime: datetime, decimal_places: int = 0):
        timestring = obstime.strftime(format="%Y-%m-%d %H:%M:%S")
        observing_time = Time(timestring)
        lat = config.Config.getValue("lat", "geography")
        lon = config.Config.getValue("lon", "geography")
        height = config.Config.getInt("height", "geography")
        observing_location = EarthLocation(lat=lat, lon=lon, height=height*u.m)
        aa = AltAz(location=observing_location, obstime=observing_time)
        equinox = config.Config.getValue("equinox", "geography")
        coord = SkyCoord(ra=str(eq_coords.ra)+"h", dec=str(eq_coords.dec)+"d", equinox=equinox, frame="fk5")
        altaz_coords = coord.transform_to(aa)
        alt = float(altaz_coords.alt / u.deg)
        az = float(altaz_coords.az / u.deg)
        if decimal_places > 0:
            alt = round(alt, decimal_places)
            az = round(az, decimal_places)
        return AltazimutalCoords(alt=alt, az=az)

    def _altaz2radec(self, aa_coords: AltazimutalCoords, obstime: datetime, decimal_places: int = 0):
        timestring = obstime.strftime(format="%Y-%m-%d %H:%M:%S")
        time = Time(timestring)
        lat = config.Config.getValue("lat", "geography")
        lon = config.Config.getValue("lon", "geography")
        height = config.Config.getInt("height", "geography")
        equinox = config.Config.getValue("equinox", "geography")
        observing_location = EarthLocation(lat=lat, lon=lon, height=height * u.m)  # type: ignore
        aa = AltAz(location=observing_location, obstime=time)
        alt_az = SkyCoord(alt=aa_coords.alt * u.deg, az=aa_coords.az * u.deg, frame=aa, equinox=equinox)  # type: ignore
        ra_dec = alt_az.transform_to('fk5')
        ra = float((ra_dec.ra / 15) / u.deg)  # type: ignore
        dec = float(ra_dec.dec / u.deg)  # type: ignore
        if decimal_places > 0:
            ra = round(ra, decimal_places)
            dec = round(dec, decimal_places)
        return EquatorialCoords(ra=ra, dec=dec)
