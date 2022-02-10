import logging
from datetime import datetime
import config
from typing import Dict
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,
    AltazimutalCoords,
    EquatorialCoords,
    PierSide,
    TelescopeSpeed,
    TelescopeResponse,
)
from astropy.coordinates import (
    EarthLocation,
    AltAz,
    SkyCoord
)
from astropy.time import Time
from astropy import units as u


logger = logging.getLogger(__name__)


class Telescope:
    def __init__(self):
        self.sync_time = None
        self.sync_status = False

    def disconnect(self) -> bool:
        """ Disconnect the server from the Telescope"""
        raise NotImplementedError()

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
        raise NotImplementedError()

    def move(self, aa_coords: AltazimutalCoords, speed: TelescopeSpeed):
        raise NotImplementedError()

    def park(self):
        self.move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("park_alt", "telescope"),
                az=config.Config.getFloat("park_az", "telescope")
            ),
            speed=TelescopeSpeed.DEFAULT
        )

    def flat(self):
        self.move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("flat_alt", "telescope"),
                az=config.Config.getFloat("flat_az", "telescope")
            ),
            speed=TelescopeSpeed.TRACKING
        )

    def get_status(self, aa_coords: AltazimutalCoords):
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
    
    def get_aa_coords(self):
        raise NotImplementedError()

    def get_eq_coords(self):
        raise NotImplementedError()

    def get_speed(self):
        raise NotImplementedError()
    
    def __radec2altaz(self, obstime: datetime, eq_coords: EquatorialCoords):
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
        coord = SkyCoord(str(eq_coords.ra)+"h", str(eq_coords.dec)+"d", equinox=self.equinox, frame="fk5")
        altaz_coords = coord.transform_to(aa)
        aa_coords = AltazimutalCoords(alt=float(altaz_coords.alt / u.deg), az=float(altaz_coords.az / u.deg))
        logger.debug("astropy altaz calculated: alt %s az %s", aa_coords.alt, aa_coords.az)
        return aa_coords

    def __altaz2radec(self, obstime: datetime, aa_cords: AltazimutalCoords):
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
        alt_az = SkyCoord(aa_cords.alt * u.deg, aa_cords.az * u.deg, frame=aa, equinox=equinox)
        ra_dec = alt_az.transform_to('fk5')
        ra = float((ra_dec.ra / 15) / u.deg)
        dec = float(ra_dec.dec / u.deg)
        logger.debug('ar park (orario decimale): %s', ra)
        logger.debug('dec park (declinazione decimale): %s', dec)
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


# class BaseTelescope:

#     def __init__(self):
#         self.max_secure_alt: int = config.Config.getFloat("max_secure_alt", "telescope")
#         self.park_alt: int = config.Config.getFloat("park_alt", "telescope")
#         self.park_az: int = config.Config.getFloat("park_az", "telescope")
#         self.flat_alt: int = config.Config.getFloat("flat_alt", "telescope")
#         self.flat_az: int = config.Config.getFloat("flat_az", "telescope")
#         self.azimut_ne = config.Config.getInt("azNE", "azimut")
#         self.azimut_se = config.Config.getInt("azSE", "azimut")
#         self.azimut_sw = config.Config.getInt("azSW", "azimut")
#         self.azimut_nw = config.Config.getInt("azNW", "azimut")
#         self.coords: Dict[str, int] = {"alt": 0, "az": 0, "tr": 0, "sl": 0, "error": 0}
#         self.status: TelescopeStatus = TelescopeStatus.PARKED
#         self.sync_status: bool = False
#         self.speed: TelescopeSpeed = TelescopeSpeed.DEFAULT
#         self.aa_coords = AltazimutalCoords()
#         self.lat = config.Config.getValue("lat", "geography")
#         self.lon = config.Config.getValue("lon", "geography")
#         self.height = config.Config.getInt("height", "geography")
#         self.equinox = config.Config.getValue("equinox", "geography")
#         self.observing_location = EarthLocation(lat=self.lat, lon=self.lon, height=self.height*u.m)
#         self.sync_time = None

#     def update_coords(self):
#         raise NotImplementedError()

#     def move_tele(self, **kwargs):
#         raise NotImplementedError()

#     def park_tele(self):
#         self.move_tele(tr=1, alt=self.park_alt, az=self.park_az)

#     def flat_tele(self):
#         self.move_tele(tr=0, alt=self.flat_alt, az=self.flat_az)

#     def read(self):
#         raise NotImplementedError()

#     def sync_tele(self):
#         raise NotImplementedError()

#     def disconnect(self):
#         raise NotImplementedError()

#     def sync(self):
#         alt_deg = config.Config.getFloat("park_alt", "telescope")
#         az_deg = config.Config.getFloat("park_az", "telescope")
#         data = self.altaz2radec(self.sync_time, alt=alt_deg, az=az_deg)
#         if self.sync_tele(**data):
#             self.sync_status = True
#         else:
#             self.sync_status = False
#         return data

#     def altaz2radec(self, obstime, alt, az):
#         logger.debug('obstime: %s', obstime)
#         timestring = obstime.strftime(format="%Y-%m-%d %H:%M:%S")
#         logger.debug("astropy timestring: %s", timestring)
#         time = Time(timestring)
#         logger.debug("astropy time: %s", time)
#         aa = AltAz(location=self.observing_location, obstime=time)
#         alt_az = SkyCoord(alt * u.deg, az * u.deg, frame=aa, equinox=self.equinox)
#         ra_dec = alt_az.transform_to('fk5')
#         ra = float((ra_dec.ra / 15) / u.deg)
#         dec = float(ra_dec.dec / u.deg)
#         logger.debug('ar park (orario decimale): %s', ra)
#         logger.debug('dec park (declinazione decimale): %s', dec)
#         return {"ra": ra, "dec": dec}

#     def radec2altaz(self, obstime, ra, dec):
#         logger.debug("astropy ra received: %s", ra)
#         logger.debug("astropy dec received: %s", dec)
#         timestring = obstime.strftime(format="%Y-%m-%d %H:%M:%S")
#         logger.debug("astropy timestring: %s", timestring)
#         observing_time = Time(timestring)
#         aa = AltAz(location=self.observing_location, obstime=observing_time)
#         coord = SkyCoord(str(ra)+"h", str(dec)+"d", equinox=self.equinox, frame="fk5")
#         altaz_coords = coord.transform_to(aa)
#         altaz_coords = {"alt": float(altaz_coords.alt / u.deg), "az": float(altaz_coords.az / u.deg)}
#         logger.debug("astropy altaz calculated: alt %s az %s", altaz_coords["alt"], altaz_coords["az"])
#         return altaz_coords

#     def nosync(self):
#         self.sync_status = False
#         self.sync_time = None

#     def __update_status__(self):

#         response = TelescopeResponse()

#         if self.coords["error"]:
#             response.status = TelescopeStatus.ERROR
#             logger.error("Errore Telescopio: "+str(self.coords['error']))
#         elif self.__within_park_alt_range__() and self.__within_park_az_range__():
#             response.status = TelescopeStatus.PARKED
#         elif self.__within_flat_alt_range__() and self.__within_flat_az_range__():
#             response.status = TelescopeStatus.FLATTER
#         elif self.coords["alt"] <= self.max_secure_alt:
#             response.status = TelescopeStatus.SECURE
#         else:
#             if self.azimut_ne > self.coords['az']:
#                 response.status = TelescopeStatus.NORTHEAST
#             elif self.coords['az'] > self.azimut_nw:
#                 response.status = TelescopeStatus.NORTHWEST
#             elif self.azimut_sw > self.coords['az'] > 180:
#                 response.status = TelescopeStatus.SOUTHWEST
#             elif 180 >= self.coords['az'] > self.azimut_se:
#                 response.status = TelescopeStatus.SOUTHEAST
#             elif self.azimut_sw < self.coords["az"] <= self.azimut_nw:
#                 response.status = TelescopeStatus.WEST
#             elif self.azimut_ne <= self.coords["az"] <= self.azimut_se:
#                 response.status = TelescopeStatus.EAST

#         if self.coords["tr"] == 1:
#             response.speed = TelescopeSpeed.TRACKING
#         elif self.coords["sl"] == 1:
#             response.speed = TelescopeSpeed.SLEWING
#         else:
#             response.speed = TelescopeSpeed.DEFAULT

#         logger.debug("Altezza Telescopio: %s", str(self.coords['alt']))
#         logger.debug("Azimut Telescopio: %s", str(self.coords['az']))
#         logger.debug("Status Telescopio: %s", str(self.status))
#         logger.debug("Status Tracking: %s %s", str(self.coords['tr']), str(self.speed))
#         logger.debug("Status slewing: %s %s", str(self.coords['sl']), str(self.speed))
#         logger.debug("Status Sync: %s ", str(self.sync_status))
#         return self.status

#     def is_within_curtains_area(self):
#         return self.status in [
#             TelescopeStatus.EAST,
#             TelescopeStatus.WEST
#         ]

#     def update_status_sync(self):
#         self.sync_status = True

#     def is_below_curtains_area(self):
#         return self.coords["alt"] <= self.max_secure_alt

#     def is_above_curtains_area(self, max_est, max_west):
#         return self.coords["alt"] >= max_est and self.coords["alt"] >= max_west

#     def __within_flat_alt_range__(self):
#         return self.__within_range__(self.coords["alt"], self.flat_alt)

#     def __within_park_alt_range__(self):
#         return self.__within_range__(self.coords["alt"], self.park_alt)

#     def __within_flat_az_range__(self):
#         return self.__within_range__(self.coords["az"], self.flat_az)

#     def __within_park_az_range__(self):
#         return self.__within_range__(self.coords["az"], self.park_az)

#     def __within_range__(self, coord, check):
#         return coord - 1 <= check <= coord + 1
