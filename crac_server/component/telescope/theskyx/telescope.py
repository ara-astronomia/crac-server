import json
import os
import re
import socket
import config
from components.telescope.telescope import BaseTelescope
from logger import Logger
from typing import Dict
from status import TelescopeStatus
from status import SyncStatus


class Telescope(BaseTelescope):

    def __init__(self):
        super().__init__()
        self.hostname = config.Config.getValue("theskyx_server")
        self.port: int = 3040
        self.script: str = os.path.join(os.path.dirname(__file__), 'get_alt_az.js')
        self.script_move_track: str = os.path.join(os.path.dirname(__file__), 'set_move_track.js')
        self.script_sync_tele: str = os.path.join(os.path.dirname(__file__), 'sync_tele.js')
        self.script_disconnect_tele: str = os.path.join(os.path.dirname(__file__), 'disconnect_tele.js')
        self.connected: bool = False

    def open_connection(self) -> None:

        if not self.connected:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.connect((self.hostname, self.port))
            self.connected = True

    def update_coords(self) -> Dict[str, int]:
        Logger.getLogger().info("Leggo le coordinate")
        data = self.__call_thesky__(self.script)
        Logger.getLogger().info("data per il update_coords: %s", data)
        Logger.getLogger().debug("Coordinate e status letti: %s", data)

        self.__parse_result__(data.decode("utf-8"))
        return self.coords

    def move_tele(self, **kwargs) -> Dict[str, int]:
        Logger.getLogger().info("muovo il telescopio")
        try:
            data = self.__call_thesky__(script=self.script_move_track, **kwargs)
            Logger.getLogger().info("data per il move_tele: %s", data)
        except (ConnectionError, TimeoutError, json.decoder.JSONDecodeError):
            self.__disconnection__()
        else:
            Logger.getLogger().debug("Parking %s", data)
            self.coords["error"] = self.__is_error__(data.decode("utf-8"))
            Logger.getLogger().info("data error per il move_tele: %s", self.coords["error"])
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

    def sync_tele(self, **kwargs) -> Dict[str, float]:
        Logger.getLogger().info("sincronizzo il telescopio")
        try:
            data = self.__call_thesky__(script=self.script_sync_tele, **kwargs)
            Logger.getLogger().info("data per il sync: %s", data)
        except (ConnectionError, TimeoutError, json.decoder.JSONDecodeError):
            self.__disconnection__()
            return False
        else:
            self.__parse_result__(data.decode("utf-8"))
            Logger.getLogger().debug("sincronizzo il telescopio a queste coordinate %s", kwargs)
            return True

    def close_connection(self) -> None:
        if self.connected:
            self.s.close()
            self.connected = False

    def disconnect(self) -> None:
        return self.__call_thesky__(script=self.script_disconnect_tele)

    def __disconnection__(self):
        Logger.getLogger().exception("Connessione con The Sky persa: ")
        self.status = TelescopeStatus.LOST
        self.connected = False

    def __call_thesky__(self, script: str, **kwargs) -> bytes:
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
            Logger.getLogger().debug("Data received from js: %s", data)
#        self.close_connection()
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
        Logger.getLogger().debug("Coords Telescopio: %s", str(self.coords))

    def __is_error__(self, input_str, search_reg="Error = ([1-9][^\\d]|\\d{2,})") -> int:
        r = re.search(search_reg, input_str)
        error_code = 0
        if r:
            r2 = re.search('\\d+', r.group(1))
            if r2:
                error_code = int(r2.group(0))
        return error_code
