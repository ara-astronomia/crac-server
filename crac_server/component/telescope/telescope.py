from abc import ABC, abstractmethod
from astropy.coordinates import (
    EarthLocation,
    AltAz,
    SkyCoord
)
from astropy.time import Time
from astropy import units as u
import logging
from datetime import datetime
from crac_server import config
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,
    AltazimutalCoords,
    EquatorialCoords,
    TelescopeSpeed,
)


logger = logging.getLogger(__name__)


class Telescope(ABC):
    def __init__(self):
        self.sync_time = None
        self.sync_status = False
        self.connected = True

    @abstractmethod
    def disconnect(self) -> bool:
        """ Disconnect the server from the Telescope"""
        raise NotImplementedError()

    @abstractmethod
    def sync(self):
        """ 
            Register the telescope in park position
            Calculate the corrisponding equatorial coordinate
        """
        raise NotImplementedError()

    def nosync(self):
        """ 
            Unregister the telescope
        """
        self.sync_time = None
        self.sync_status = False

    @abstractmethod
    def move(self, aa_coords: AltazimutalCoords, speed: TelescopeSpeed):
        raise NotImplementedError()
    
    @abstractmethod
    def set_speed(self, speed: TelescopeSpeed):
        raise NotImplementedError()

    @abstractmethod
    def get_aa_coords(self) -> AltazimutalCoords:
        raise NotImplementedError()

    @abstractmethod
    def get_eq_coords(self) -> EquatorialCoords:
        raise NotImplementedError()

    @abstractmethod
    def get_speed(self) -> TelescopeSpeed:
        raise NotImplementedError()

    def park(self, speed=TelescopeSpeed.SPEED_NOT_TRACKING):
        self.move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("park_alt", "telescope"),
                az=config.Config.getFloat("park_az", "telescope")
            ),
            speed=speed
        )

    def flat(self, speed=TelescopeSpeed.SPEED_NOT_TRACKING):
        self.move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("flat_alt", "telescope"),
                az=config.Config.getFloat("flat_az", "telescope")
            ),
            speed=speed
        )

    def get_status(self, aa_coords: AltazimutalCoords) -> TelescopeStatus:
        if not aa_coords or not aa_coords.alt or not aa_coords.az:
            logger.error("Errore Telescopio: "+str(aa_coords))
            return TelescopeStatus.ERROR
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

    def __radec2altaz(self, eq_coords: EquatorialCoords, obstime: datetime):
        logger.debug("astropy ra received: %s", eq_coords.ra)
        logger.debug("astropy dec received: %s", eq_coords.dec)
        timestring = obstime.strftime(format="%Y-%m-%d %H:%M:%S")
        logger.debug("astropy timestring: %s", timestring)
        observing_time = Time(timestring)
        lat = config.Config.getValue("lat", "geography")
        lon = config.Config.getValue("lon", "geography")
        height = config.Config.getInt("height", "geography")
        observing_location = EarthLocation(lat=lat, lon=lon, height=height*u.m)
        aa = AltAz(location=observing_location, obstime=observing_time)
        equinox = config.Config.getValue("equinox", "geography")
        coord = SkyCoord(ra=str(eq_coords.ra)+"h", dec=str(eq_coords.dec)+"d", equinox=equinox, frame="fk5")
        altaz_coords = coord.transform_to(aa)
        aa_coords = AltazimutalCoords(alt=float(altaz_coords.alt / u.deg), az=float(altaz_coords.az / u.deg))
        logger.debug("astropy altaz calculated: alt %s az %s", aa_coords.alt, aa_coords.az)
        return aa_coords

    def __altaz2radec(self, aa_coords: AltazimutalCoords, decimal_places: int, obstime: datetime):
        logger.debug('obstime: %s', obstime)
        timestring = obstime.strftime(format="%Y-%m-%d %H:%M:%S")
        logger.debug("astropy timestring: %s", timestring)
        time = Time(timestring)
        logger.debug("astropy time: %s", time)
        lat = config.Config.getValue("lat", "geography")
        lon = config.Config.getValue("lon", "geography")
        height = config.Config.getInt("height", "geography")
        equinox = config.Config.getValue("equinox", "geography")
        observing_location = EarthLocation(lat=lat, lon=lon, height=height*u.m)
        aa = AltAz(location=observing_location, obstime=time)
        alt_az = SkyCoord(alt=aa_coords.alt * u.deg, az=aa_coords.az * u.deg, frame=aa, equinox=equinox)
        ra_dec = alt_az.transform_to('fk5')
        ra = float((ra_dec.ra / 15) / u.deg)
        dec = float(ra_dec.dec / u.deg)
        logger.debug('ar park (orario decimale): %s', ra)
        logger.debug('dec park (declinazione decimale): %s', dec)
        if decimal_places:
            ra = round(ra, decimal_places)
            dec = round(dec, decimal_places)
        return EquatorialCoords(ra=ra, dec=dec)

    def is_below_curtains_area(self, alt: float) -> bool:
        return alt <= config.Config.getFloat("max_secure_alt", "telescope")

    def is_above_curtains_area(self, alt: float, max_est: int, max_west: int) -> bool:
        return alt >= max_est and alt >= max_west

    def is_within_curtains_area(self, aa_coords: AltazimutalCoords) -> bool:
        return self.get_status(aa_coords) in [
            TelescopeStatus.EAST,
            TelescopeStatus.WEST
        ]

    def __within_flat_alt_range(self, alt: float):
        return self.__within_range(alt, config.Config.getFloat("flat_alt", "telescope"))

    def __within_park_alt_range(self, alt: float):
        return self.__within_range(alt, config.Config.getFloat("park_alt", "telescope"))

    def __within_flat_az_range(self, az: float):
        return self.__within_range(az, config.Config.getFloat("flat_az", "telescope"))

    def __within_park_az_range(self, az: float):
        return self.__within_range(az, config.Config.getFloat("park_az", "telescope"))

    def __within_range(self, coord: float, check: float):
        return coord - 1 <= check <= coord + 1
