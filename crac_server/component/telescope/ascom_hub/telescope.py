from datetime import datetime
from typing import Any
from crac_server.component.telescope.telescope import Telescope as TelescopeBase
from crac_server import config
from crac_protobuf.telescope_pb2 import (
    EquatorialCoords,
    AltazimutalCoords,
    TelescopeSpeed,
)
import requests

class Telescope(TelescopeBase):

    # default port 11111
    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        super().__init__(hostname=hostname, port=port)
        self._base_path = "/telescope/" + config.Config.getValue("device_number", "ascom_hub")
        self.client_transaction_id = 0
    
    def sync(self, started_at: datetime):
        eq_coords = self._calculate_eq_coords_of_park_position(started_at)
        self._put_response("synctocoordinates", {"RightAscension": eq_coords.ra, "Declination": eq_coords.dec})  # type: ignore
        self._put_response("setpark")

    def set_speed(self, speed: TelescopeSpeed):  # type: ignore
        if self.has_tracking_off_capability:
            tracking = False if speed is TelescopeSpeed.SPEED_NOT_TRACKING else True  # type: ignore
            self._put_response("tracking", {"Tracking": tracking})

    def park(self, speed: TelescopeSpeed):  # type: ignore
        self._put_response("park")
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING and self.has_tracking_off_capability:  # type: ignore
            self._put_response("tracking", {"Tracking": False})

    def flat(self, speed: TelescopeSpeed):  # type: ignore
        alt_deg = config.Config.getFloat("flat_alt", "telescope")
        az_deg = config.Config.getFloat("flat_az", "telescope")
        self._put_response("slewtoaltaz", {"Azimuth": az_deg, "Altitude": alt_deg})

    def retrieve(self):
        aa_coords = self._retrieve_aa_coords()
        eq_coords = self._retrieve_eq_coords()
        speed = self._retrieve_speed()
        status = self._retrieve_status(aa_coords)
        return (eq_coords, aa_coords, speed, status)

    def _retrieve_aa_coords(self):
        altitude_response = self._get_response("altitude")
        azimut_response = self._get_response("azimut")
        return AltazimutalCoords(alt=float(altitude_response.json().value), az=float(azimut_response.json().value))

    def _retrieve_eq_coords(self):
        declination_response = self._get_response("declination")
        right_ascension_response = self._get_response("rightascension")
        return EquatorialCoords(alt=float(declination_response.json().value), az=float(right_ascension_response.json().value))

    def _retrieve_speed(self):
        tracking_response = self._get_response("tracking")
        slewing_response = self._get_response("slewing")
        if tracking_response and slewing_response:
            return TelescopeSpeed.SPEED_ERROR  # type: ignore
        elif tracking_response:
            return TelescopeSpeed.SPEED_TRACKING  # type: ignore
        elif slewing_response:
            return TelescopeSpeed.SPEED_SLEWING  # type: ignore
        else:
            return TelescopeSpeed.SPEED_NOT_TRACKING  # type: ignore

    def _get_response(self, what):
        data = self._merge_client_information()
        return requests.get(self._hostname + self._base_path + what, data)

    def _put_response(self, what, data: dict[str, Any] = {}, client_transaction_id=0):
        data = self._merge_client_information(data)
        return requests.put(self._hostname + self._base_path + what, data=data)
    
    def _merge_client_information(self, data: dict[str, Any] = {}):
        self.client_transaction_id = self.client_transaction_id + 1
        return data | {"ClientId": 154, "ClientTransactionID": self.client_transaction_id}
