from datetime import datetime
from crac_protobuf.telescope_pb2 import (
    TelescopeStatus,
    TelescopeSpeed,
    AltazimutalCoords,
)
from crac_server import config
from crac_server.component.telescope.telescope import Telescope as TelescopeBase
import logging
import json
import os
import re
from typing import Dict


logger = logging.getLogger(__name__)


class Telescope(TelescopeBase):

    # default port 3040
    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")):
        super().__init__(hostname=hostname, port=port)
        self.script = os.path.join(os.path.dirname(__file__), 'get_alt_az.js')
        self.script_move_track = os.path.join(os.path.dirname(__file__), 'set_move_track.js')
        self.script_sync_tele = os.path.join(os.path.dirname(__file__), 'sync_tele.js')
        self.script_disconnect_tele = os.path.join(os.path.dirname(__file__), 'disconnect_tele.js')

    def sync(self, **kwargs) -> Dict[str, float]:
        aa_coords = AltazimutalCoords(
            alt=config.Config.getFloat("park_alt", "telescope"),
            az=config.Config.getFloat("park_az", "telescope")
        )
        eq_coords = self._altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow())
        self.__call(script=self.script_sync_tele, ra=eq_coords.ra, dec=eq_coords.dec)
    
    def set_speed(self, speed: TelescopeSpeed):
        tr = 1 if speed is TelescopeSpeed.SPEED_NOT_TRACKING else 0
        self.__call(script=self.script_move_track, tr=tr)
    
    def park(self, speed=TelescopeSpeed.SPEED_NOT_TRACKING):
        tr = 1 if speed is TelescopeSpeed.SPEED_NOT_TRACKING else 0
        alt_deg = config.Config.getFloat("park_alt", "telescope")
        az_deg = config.Config.getFloat("park_az", "telescope")
        self.__call(script=self.script_move_track, tr=tr, alt=alt_deg, az=az_deg)

    def flat(self, speed=TelescopeSpeed.SPEED_NOT_TRACKING):
        tr = 1 if speed is TelescopeSpeed.SPEED_NOT_TRACKING else 0
        alt_deg = config.Config.getFloat("park_alt", "telescope")
        az_deg = config.Config.getFloat("park_az", "telescope")
        self._call(script=self.script_move_track, tr=tr, alt=alt_deg, az=az_deg)

    def retrieve(self) -> tuple:
        data = self.__call(script=self.script)
        aa_coords, speed = self.__parse_result(data)
        eq_coords = self._altaz2radec(aa_coords=aa_coords, decimal_places=2, obstime=datetime.utcnow())
        aa_coords = self._retrieve_aa_coords(eq_coords)
        status = self._retrieve_status(aa_coords)

        return (eq_coords, aa_coords, speed, status)

    def __call(self, script: str, **kwargs) -> dict:
        with open(script, 'r') as p:
            file = p.read()
            if kwargs:
                if kwargs.get("az") is None:
                    kwargs["az"] = ""
                if kwargs.get("alt") is None:
                    kwargs["alt"] = ""
                file = file.format(**kwargs)
            self.s.sendall(file.encode('utf-8'))

        data = self.s.recv(1024).decode("utf-8")
        logger.debug(f"Data received from js: {data}")
        jsonStringEnd = data.find("|")
        jsonString = data[:jsonStringEnd]
        try:
            return json.loads(jsonString)
        except json.decoder.JSONDecodeError as err:
            logger.error(f"Json Malformed {err}")
            raise err

    def __parse_result(self, jsonLoad: dict) -> tuple:
        #coords["error"] = self.__is_error__(jsonLoad)

        #if not self.coords["error"]:
        aa_coords = AltazimutalCoords(alt=round(jsonLoad["alt"], 2), az=round(jsonLoad["az"], 2))
        if jsonLoad["tr"] == 1 and jsonLoad["sl"] == 1:
            speed = TelescopeSpeed.SPEED_NOT_TRACKING 
        elif jsonLoad["tr"] == 1 and jsonLoad["sl"] == 0:
            speed = TelescopeSpeed.SPEED_SLEWING
        elif jsonLoad["tr"] == 0 and jsonLoad["sl"] == 1:
            speed = TelescopeSpeed.SPEED_TRACKING
        else:
            speed = TelescopeSpeed.SPEED_ERROR
        
        return (aa_coords, speed)
        
    # def __is_error__(self, input_str, search_reg="Error = ([1-9][^\\d]|\\d{2,})") -> int:
    #     r = re.search(search_reg, input_str)
    #     error_code = 0
    #     if r:
    #         r2 = re.search('\\d+', r.group(1))
    #         if r2:
    #             error_code = int(r2.group(0))
    #     return error_code
