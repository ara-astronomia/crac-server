import logging
import socket
from abc import ABC, abstractmethod
from astropy import units as u
from astropy.coordinates import (
    EarthLocation,
    AltAz,
    SkyCoord
)
from astropy.time import Time, TimeDelta
from collections import deque
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,  # type: ignore
    AltazimutalCoords,  # type: ignore
    EquatorialCoords,  # type: ignore
    TelescopeSpeed,  # type: ignore
    Airmass, # type: ignore
    Transit, # type: ignore
)
from crac_server import config
from datetime import datetime
from threading import Thread
from time import sleep
import numpy as np

logger = logging.getLogger(__name__)


class Telescope(ABC):

    def __init__(self, hostname: str = None, port: int = None) -> None:  # type: ignore
        self._hostname = hostname
        self._port = port
        self._polling = False
        self._jobs = deque()
        self._has_tracking_off_capability = config.Config.getBoolean("tracking_off", "telescope")
        self._connection_retry = 0
        self._flat_coordinate = AltazimutalCoords(alt=config.Config.getFloat("flat_alt", "telescope"), az=config.Config.getFloat("flat_az", "telescope"))
        self._reset()

    @abstractmethod
    def sync(self, started_at: datetime):
        """ 
            Register the telescope in park position
            Calculate the corrisponding equatorial coordinate
        """

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
    def retrieve(self) -> tuple:
        """ Retrieve coordinate and speed from the Telescope """
    
    def polling_start(self):
        if not self._polling:
            self._polling = True
            self.t = Thread(target=self.__read)
            self.t.start()
    
    def polling_end(self):
        if self._polling:
            self._polling = False
            self.t.join()
    
    def queue_sync(self, started_at: datetime):
        self._jobs.append({"action": self.sync, "started_at": started_at})
    
    def queue_set_speed(self, speed: TelescopeSpeed):
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING and not self.has_tracking_off_capability:
            speed = TelescopeSpeed.SPEED_TRACKING
        self._jobs.append({"action": self.set_speed, "speed": speed})
    
    def queue_park(self):
        speed = TelescopeSpeed.SPEED_NOT_TRACKING if self.has_tracking_off_capability else TelescopeSpeed.SPEED_TRACKING
        self._jobs.append({"action": self.park, "speed": speed})

    def queue_flat(self):
        speed = TelescopeSpeed.SPEED_NOT_TRACKING if self.has_tracking_off_capability else TelescopeSpeed.SPEED_TRACKING
        self._jobs.append({"action": self.flat, "speed": speed})
    
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

    def __open_connection(self) -> bool:
        """ Connect the server to the Telescope """

        if not self._hostname or not self._port:
            return True 
        try:
            #self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s = socket.create_connection((self._hostname, self._port), timeout=2)
            return True
        except (ConnectionRefusedError, socket.error, socket.herror, TimeoutError) as e: 
            logger.error(f"Connection error: {e}", exc_info=1)
            return False
        except:
            logger.error("Generic connection error", exc_info=1)
            return False

    def __disconnect(self):
        """ Disconnect the server from the Telescope"""
        if not self._hostname or not self._port:
            return

        if self.status is not TelescopeStatus.LOST:  # type: ignore
            self.s.close()

    def __read(self):
        """ 
            Polling the Telescope for coordinate and speed
            If there are some actions to do like move it or sync it
            then they will be dequeued and worked here
        """

        while self._polling:
            if not self.__open_connection():
                self.status = TelescopeStatus.LOST
                continue

            try:
                if len(self._jobs) > 0:
                    logger.debug(f"there are {len(self._jobs)} jobs: {self._jobs}")
                    job = self._jobs.popleft()
                    args = {key: val for key ,val in job.items() if key != "action"}
                    job['action'](**args)

                self.eq_coords, self.aa_coords, self.airmass, self.transit, self.speed, self.status = self.retrieve()
            except:
                logger.error("Error in completing job", exc_info=1)
                self.status = TelescopeStatus.ERROR
                continue
            finally:
                self.__disconnect()
                sleep(config.Config.getFloat("polling_interval", "telescope"))
        else:
            self._reset()
            self.__disconnect()

    def _reset(self):
        self.status = TelescopeStatus.DISCONNECTED
        self.eq_coords: EquatorialCoords = None
        self.aa_coords: AltazimutalCoords = None
        self.airmass : Airmass = None
        self.transit: Transit = None
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
    
    def _calculate_eq_coords_of_park_position(self, started_at: datetime) -> EquatorialCoords:
        aa_coords = AltazimutalCoords(
            alt=config.Config.getFloat("park_alt", "telescope"), 
            az=config.Config.getFloat("park_az", "telescope")
        )
        logger.debug(f"This is the aa coordinate for park position: {aa_coords}")
        return self._calculate_telescope_position(
            aa_coords=aa_coords, 
            started_at=started_at, 
            decimal_places=2,
            speed=self.speed
        )

    def _calculate_telescope_position(self, aa_coords: AltazimutalCoords, started_at: datetime, decimal_places: int, speed: TelescopeSpeed = TelescopeSpeed.SPEED_TRACKING) -> EquatorialCoords:
        started_at = datetime.utcnow() if started_at is None else started_at
        eq_coords = self._altaz2radec(
            aa_coords=aa_coords, 
            obstime=started_at
        )
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:  # type: ignore
            timestamp_started_at = datetime.timestamp(started_at)
            timestamp_now = datetime.timestamp(datetime.utcnow())
            delta_timestamp = timestamp_now - timestamp_started_at
            ra = (delta_timestamp / 3600) + eq_coords.ra
            synced_eq_coords = EquatorialCoords(ra=round(ra, decimal_places), dec=round(eq_coords.dec, decimal_places))
            logger.debug(f"equatorial coordinate for synced position when telescope is not tracking {synced_eq_coords}")
            return synced_eq_coords
        logger.debug(f"equatorial coordinate for synced position when telescope is tracking  {eq_coords}")
        synced_eq_coords = EquatorialCoords(ra=round(eq_coords.ra, decimal_places), dec=round(eq_coords.dec, decimal_places))
        return synced_eq_coords

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

    def _airmass (self, alt_az: AltazimutalCoords,):
        lat = config.Config.getValue("lat", "geography")
        lon = config.Config.getValue("lon", "geography")
        height = config.Config.getInt("height", "geography")
        observing_location = EarthLocation(lat=lat, lon=lon, height=height*u.m)  
        obstime=Time.now()
        alt=alt_az.alt
        altezza = alt * u.deg
        azimuth =0 * u.deg
        altaz_frame=AltAz(alt=altezza, az=azimuth, location=observing_location,obstime=obstime)
        airmass_float = altaz_frame.secz
        airmass = round((float(airmass_float)), 3)
        logger.debug(f"questo è il valore di airmass calcolato: {airmass}")
        return Airmass(airmass=airmass)

    def _transit (self, eq_coords: EquatorialCoords):
        lat = config.Config.getValue("lat", "geography")
        lon = config.Config.getValue("lon", "geography")
        height = config.Config.getInt("height", "geography")
        observing_location = EarthLocation(lat=lat, lon=lon, height=height*u.m)  
        obstime=Time.now()
        print (f"valore di time now: {obstime}")
        print(eq_coords)
        print (f"type eq_coords from protobuf:{(type(eq_coords))}")
        coord = SkyCoord(ra=(eq_coords.ra)* u.deg, dec=(eq_coords.dec)* u.deg, frame="icrs")
        print(coord)
        print (f"type coord from astropy SkyCoord: {(type(coord))}")
        local_sidereal_time = obstime.sidereal_time('apparent', longitude=observing_location.lon)
        print (f" questo è il tempo siderale locale: {local_sidereal_time}")
        #coord_ra=coord.ra * u.hour
        print (coord.ra)
        print(f" formato di coord.ra :{(type(coord.ra))}")
        hour_angle = (local_sidereal_time - coord.ra).wrap_at(24 * u.hour)
        print (hour_angle)
        print(f"type hour_angle: {(type(hour_angle))}")
        hour_angle_in_time = TimeDelta(hour_angle.hour * u.hour)
        print (f"qusto è il valore dell'angolo orario: {hour_angle_in_time}")
        transit_time = obstime - hour_angle_in_time
        print(f"Il tempo di transito al meridiano è: {transit_time}")
        transit_timestamp=str(transit_time) #.unix
        print(transit_timestamp)
        return Transit(transit=transit_timestamp)


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
