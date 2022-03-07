from datetime import datetime
import threading
from component.telescope.telescope import Telescope as BaseTelescope
from crac_protobuf.telescope_pb2 import TelescopeStatus
from crac_server import config
import logging
import json
import os
import re
import socket
from typing import Dict


logger = logging.getLogger(__name__)
lock = threading.Lock()


class Telescope(BaseTelescope):

    def __init__(self, hostname=config.Config.getValue("theskyx_ip", "server"), port=3040):
        super().__init__(hostname=hostname, port=port)
        self.script = os.path.join(os.path.dirname(__file__), 'get_alt_az.js')
        self.script_move_track = os.path.join(os.path.dirname(__file__), 'set_move_track.js')
        self.script_sync_tele = os.path.join(os.path.dirname(__file__), 'sync_tele.js')
        self.script_disconnect_tele = os.path.join(os.path.dirname(__file__), 'disconnect_tele.js')

    def sync(self, **kwargs) -> Dict[str, float]:
        logger.info("sincronizzo il telescopio")
        alt_deg = config.Config.getFloat("park_alt", "telescope")
        az_deg = config.Config.getFloat("park_az", "telescope")
        self.sync_time = datetime.utcnow()
        eq_coords = self.altaz2radec(self.sync_time, alt=alt_deg, az=az_deg)
        try:
            data = self.__call_thesky__(script=self.script_sync_tele, ra=eq_coords.ra, dec=eq_coords.dec)
            logger.info("data per il sync: %s", data)
        except (ConnectionError, TimeoutError, json.decoder.JSONDecodeError):
            self.__disconnection__()
            self.sync_status = False
        else:
            self.__parse_result__(data.decode("utf-8"))
            logger.debug("sincronizzo il telescopio a queste coordinate %s", kwargs)
            self.sync_status = True

    def update_coords(self) -> Dict[str, int]:
        logger.info("Leggo le coordinate")
        data = self.__call_thesky__(self.script)
        logger.info("data per il update_coords: %s", data)
        logger.debug("Coordinate e status letti: %s", data)

        self.__parse_result__(data.decode("utf-8"))
        return self.coords

    def move_tele(self, **kwargs) -> Dict[str, int]:
        logger.info("muovo il telescopio")
        try:
            data = self.__call_thesky__(script=self.script_move_track, **kwargs)
            logger.info("data per il move_tele: %s", data)
        except (ConnectionError, TimeoutError, json.decoder.JSONDecodeError):
            self.__disconnection__()
        else:
            logger.debug("Parking %s", data)
            self.coords["error"] = self.__is_error__(data.decode("utf-8"))
            logger.info("data error per il move_tele: %s", self.coords["error"])
            self.update_coords()
            self.__update_status__()
            self.coords

    def read(self):
        try:
            self.update_coords()
        except (ConnectionError, TimeoutError, json.decoder.JSONDecodeError):
            self.__disconnection__()
        else:
            self.__update_status__()

    def __disconnection__(self):
        logger.exception("Connessione con The Sky persa: ")
        self.status = TelescopeStatus.LOST
        self.connected = False
        self.disconnect()

    def __call_thesky__(self, script: str, **kwargs) -> bytes:
        with lock:
            self.open_connection()
            with open(script, 'r') as p:
                file = p.read()
                if kwargs:
                    if kwargs.get("az") is None:
                        kwargs["az"] = ""
                    if kwargs.get("alt") is None:
                        kwargs["alt"] = ""
                    file = file.format(**kwargs)
                self.s.sendall(file.encode('utf-8'))
                data = self.s.recv(1024)
                logger.debug("Data received from js: %s", data)
           self.close_connection()
        return data

    def __parse_result__(self, data: str):

        self.coords["error"] = self.__is_error__(data)

        if not self.coords["error"]:
            jsonStringEnd = data.find("|")
            jsonString = data[:jsonStringEnd]
            coords = json.loads(jsonString)
            self.coords["alt"] = round(coords["alt"], 2)
            self.coords["az"] = round(coords["az"], 2)
            self.coords["tr"] = coords["tr"]
            self.coords["sl"] = coords["sl"]
        logger.debug("Coords Telescopio: %s", str(self.coords))

    def __is_error__(self, input_str, search_reg="Error = ([1-9][^\\d]|\\d{2,})") -> int:
        r = re.search(search_reg, input_str)
        error_code = 0
        if r:
            r2 = re.search('\\d+', r.group(1))
            if r2:
                error_code = int(r2.group(0))
        return error_code
