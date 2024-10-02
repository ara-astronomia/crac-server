from datetime import datetime
import logging
from typing import Any
from crac_server.component.telescope.telescope import Telescope as TelescopeBase
from crac_server import config
from crac_protobuf.telescope_pb2 import (
    EquatorialCoords,
    AltazimutalCoords,
    TelescopeSpeed,
)
import requests


logger = logging.getLogger(__name__)


class Telescope(TelescopeBase):

    # default port 11111
    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        super().__init__(hostname="http://" + hostname, port=port)
        self._base_path = "/api/v1/telescope/" + config.Config.getValue("device_number", "ascom_hub") + "/"
        self.client_transaction_id = 0
    
    def sync(self, started_at: datetime):
        self._unpark_and_track()
        eq_coords = self._calculate_eq_coords_of_park_position(started_at)
        logger.debug(f"Coordinates for syncing: ra: {eq_coords.ra} dec: {eq_coords.dec}")  # type: ignore
        self._put_response("synctocoordinates", {"RightAscension": eq_coords.ra, "Declination": eq_coords.dec})  # type: ignore
        self._put_response("setpark")

    def set_speed(self, speed: TelescopeSpeed):  # type: ignore
        if self.has_tracking_off_capability:
            tracking = False if speed is TelescopeSpeed.SPEED_NOT_TRACKING else True  # type: ignore
            self._put_response("tracking", {"Tracking": tracking})

    def park(self, speed: TelescopeSpeed = None):  # type: ignore
        self._park_and_untrack()

    def flat(self, speed: TelescopeSpeed = None):  # type: ignore
        self._unpark_and_track()
        eq_coords = self._altaz2radec(aa_coords=self._flat_coordinate, obstime=datetime.utcnow(), decimal_places=2)
        logger.debug(f"Coordinates for flat: ra: {eq_coords.ra} dec: {eq_coords.dec}")  # type: ignore
        self._put_response("slewtocoordinates", {"RightAscension": eq_coords.ra, "Declination": eq_coords.dec})
        self._put_response("tracking", {"Tracking": False})

    def retrieve(self):
        aa_coords = self._retrieve_aa_coords()
        eq_coords = self._retrieve_eq_coords()
        speed = self._retrieve_speed()
        status = self._retrieve_status(aa_coords)
        indicators = (eq_coords, aa_coords, speed, status)
        logger.debug("those are the indicators")
        logger.debug(indicators)
        return indicators

    def _unpark_and_track(self):
        self.set_speed(TelescopeSpeed.SPEED_TRACKING)
        self._put_response("unpark")
    
    def _park_and_untrack(self):
        self._put_response("park")
        self.set_speed(TelescopeSpeed.SPEED_NOT_TRACKING)

    def _retrieve_aa_coords(self):
        altitude_response = self._get_response("altitude")
        azimuth_response = self._get_response("azimuth")
        return AltazimutalCoords(alt=float(altitude_response.json()["Value"]), az=float(azimuth_response.json()["Value"]))

    def _retrieve_eq_coords(self):
        declination_response = self._get_response("declination")
        right_ascension_response = self._get_response("rightascension")
        return EquatorialCoords(dec=float(declination_response.json()["Value"]), ra=float(right_ascension_response.json()["Value"]))

    def _retrieve_speed(self):
        is_tracking = bool(self._get_response("tracking").json()["Value"])
        is_slewing = bool(self._get_response("slewing").json()["Value"])
        logger.debug(f"tracking value: {is_tracking}")
        logger.debug(f"slewing value: {is_slewing}")
        if is_tracking and is_slewing:
            return TelescopeSpeed.SPEED_ERROR  # type: ignore
        elif is_tracking:
            return TelescopeSpeed.SPEED_TRACKING  # type: ignore
        elif is_slewing:
            return TelescopeSpeed.SPEED_SLEWING  # type: ignore
        else:
            return TelescopeSpeed.SPEED_NOT_TRACKING  # type: ignore

    def _get_response(self, what):
        url = self._hostname + ":" + str(self._port) + self._base_path + what
        logger.debug(f"get request sent to {url}: {what}")
        params = self._merge_client_information()
        response = requests.get(url, params=params)
        logger.debug(f"get response received from {url}: {response}")
        return response

    def _put_response(self, what, data: dict[str, Any] = {}):
        url = self._hostname + ":" + str(self._port) + self._base_path + what
        logger.debug(f"put request sent to {url}: {what}")
        data = self._merge_client_information(data)
        response = requests.put(self._hostname + ":" + str(self._port) + self._base_path + what, data=data)
        logger.debug(f"put response received from {url}: {response}")
        return response
    
    def _merge_client_information(self, data: dict[str, Any] = {}):
        self.client_transaction_id = self.client_transaction_id + 1
        return data | {"ClientId": 154, "ClientTransactionID": self.client_transaction_id}

    def __open_connection(self):
        return True

    def __disconnect(self):
        pass
