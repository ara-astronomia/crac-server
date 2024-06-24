from datetime import datetime
from crac_protobuf.telescope_pb2 import (
    EquatorialCoords,
    AltazimutalCoords,
    TelescopeSpeed,
)
from crac_server import config
from crac_server.component.telescope.telescope import Telescope as TelescopeBase
import logging
import json
import re
import os
import time
import socket
import xml.etree.ElementTree as ET
logger = logging.getLogger(__name__)


class Telescope(TelescopeBase):

    # default port 7624
    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        super().__init__(hostname=hostname, port=port)
        self._name = config.Config.getValue("name", "indigo")
    
    def sync(self, started_at: datetime):
        self.__call(
            f"""
                <setNumberVector device="{self._name}" name="MOUNT_ON_COORDINATES_SET">
                    <oneNumber name="SLEW">
                        Off
                    </oneNumeber>
                    <oneNumber name="TRACK">
                        Off
                    </oneNumber>
                    <oneNumber name="SYNC">
                        On
                    </oneNumber>
                </oneNumberVector>
            """
        )
        eq_coords = self._calculate_eq_coords_of_park_position(started_at)
        self.__call(
            f"""
                <defNumberVector device="{self._name}" name="MOUNT_EQUATORIAL_COORDINATES">
                    <oneNumber name="DEC">
                      {eq_coords.dec}
                    </oneNumber>
                    <oneNumber name="RA">
                      {eq_coords.ra}
                    </oneNumber>
                </defNumberVector>
            """
        )
        self.__call(
            f"""
                <oneNumberVector device="{self._name}" name="MOUNT_ON_COORDINATES_SET">
                    <oneNumber name="SLEW">
                        Off
                    </oneNumber>
                    <oneNumber name="TRACK">
                        On
                    </oneNumber>
                    <oneNumber name="SYNC">
                        Off
                    </oneNumber>
                </oneNumberVector>
            """
        )

    def set_speed(self, speed: TelescopeSpeed):
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            self.__call(
                f"""
                    <oneNumberVector device="{self._name}" name="MOUNT_TRACKING">
                        <oneNumber name="OFF">
                            On
                        </oneNumber>
                    </oneNumberVector>
                """
            )
        else:
            self.__call(
                f"""
                    <oneNumberVector device="{self._name}" name="MOUNT_TRAKING">
                        <oneNumber name="ON">
                            On
                        </oneNumber>
                    </oneNumberVector>
                """
            )
            self.__call(
                f"""
                    <oneNumberVector device="{self._name}" name="MOUNT_ON_COORDINATES_SET">
                        <oneNumber name="SLEW">
                            {"On" if speed == TelescopeSpeed.SPEED_SLEWING else "Off"}
                        </oneNumber>
                        <oneNumber name="TRACK">
                            {"On" if speed == TelescopeSpeed.SPEED_TRACKING else "Off"}
                        </oneNumber>
                        <oneNumber name="SYNC">
                            Off
                        </oneNumber>
                    </oneNumberVector>
                """
            )

    def park(self, speed: TelescopeSpeed):
        self.__move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("park_alt", "telescope"),
                az=config.Config.getFloat("park_az", "telescope")
            ),
            speed=speed
        )
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            self.__call(
                f"""
                <oneNumberVector device="{self._name}" name="MOUNT_TRACKING">
                    <oneNumber name="OFF">
                        On
                    </oneNumber>
                </oneNumberVector>
                """
            )

    def flat(self, speed: TelescopeSpeed):
        self.__move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("flat_alt", "telescope"),
                az=config.Config.getFloat("flat_az", "telescope")
            ),
            speed=speed
        )
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            self.__call(
                f"""
                <oneNumberVector device="{self._name}" name="MOUNT_TRACKING">
                    <oneNumber name="OFF">
                        On
                    </oneNumber>
                </oneNumberVector>
                """
            )

    def retrieve(self) -> tuple:
        root = self.__call(request_data)
           
        print(f"questo è il valore di root {root}")
        eq_coords = self.__retrieve_eq_coords(root)   
        logger.debug(f"data received from json: {eq_coords}")     
        speed = self.__retrieve_speed(root)
        logger.debug(f"data received from json: {speed}")
        aa_coords = self._retrieve_aa_coords(eq_coords)
        logger.debug(f"data received from json: {aa_coords}")
        status = self._retrieve_status(aa_coords)
        logger.debug(f"data received from json: {status}")

        return (eq_coords, aa_coords, speed, status)

    def __move(self, aa_coords: AltazimutalCoords, speed=TelescopeSpeed.SPEED_TRACKING):
        self.__call(
            f"""
                <oneNumberVector device="{self._name}" name="MOUNT_PARK">
                    <oneNumber name="UNPARKED">
                        On
                    </oneNumber>
                </oneNumberVector>
            """
        )
        eq_coords = self._altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow()) if isinstance(aa_coords, (AltazimutalCoords)) else aa_coords
        logger.debug(aa_coords)
        logger.debug(eq_coords)
        self.queue_set_speed(speed)
        self.__call(
            f"""
                <defNumberVector device="{self._name}" name="MOUNT_EQUATORIAL_COORDINATES">
                    <defNumber name="DEC">
                      {eq_coords.dec}
                    </defNumber>
                    <defNumber name="RA">
                      {eq_coords.ra}
                    </defNumber>
                </defNumberVector>
            """
        )

    def __retrieve_speed(self, root):
        state = root.attrib["state"].strip() if root else None
        if state == "Ok":
            return TelescopeSpeed.SPEED_TRACKING
        elif state == "Idle":
            return TelescopeSpeed.SPEED_NOT_TRACKING
        elif state == "Busy":
            return TelescopeSpeed.SPEED_SLEWING
        else:
            return TelescopeSpeed.SPEED_ERROR
        # match state:
        #     case "Ok":
        #         return TelescopeSpeed.SPEED_TRACKING
        #     case "Idle":
        #         return TelescopeSpeed.SPEED_NOT_TRACKING
        #     case "Busy":
        #         return TelescopeSpeed.SPEED_SLEWING
        #     case _:
        #         return TelescopeSpeed.SPEED_ERROR

    def __retrieve_eq_coords(self, root):
        ra, dec = None, None
        seen = set()

        for item in root:
            if "setNumberVector" in item:
                vector = item["setNumberVector"]
                if vector["name"] == "MOUNT_EQUATORIAL_COORDINATES":
                    #print(f"Processing vector: {vector['name']}")  # Debug
                    for coord in vector["items"]:
                        key = (vector["name"], coord["name"], coord["value"])
                        logger.debug(f" questa è la key richiesta {key}") 
                        if key not in seen:
                            seen.add(key)
                            if coord["name"] == "RA":
                                logger.debug(f"RA: {coord['value']}")
                                ra = {coord['value']}
                            elif coord["name"] == "DEC":
                                logger.debug(f"DEC: {coord['value']}")
                                dec = {coord['value']}
                    if ra and dec:
                        return EquatorialCoords(ra=ra, dec=dec)
                    else:
                        raise Exception(f"RA or Dec not present. RA: {ra}, DEC: {dec}")

    def __call(self, script):
        print(f"QUESTO DOVREBBE ESSERE IL VALORE DI SCRIPT {script}")
        request_json = json.dumps(script)
        print(f"Request JSON: {request_json}")
    
        # Create a socket object
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(5.0)  # Set a timeout for the socket

        try:
            self.s.sendall(request_json.encode('utf-8'))
            time.sleep(1)
            response=b""
            buffer=""
            while True:
                try:
                    part = self.s.recv(30000)
                    if not part:
                        break
                    response += part
                except socket.timeout:
                    print("Socket timeout, stopping reception.")
                    break
                
                # Decode the received data
                response_json = response.decode('utf-8')
                #print(f"Response JSON: {response_json}")  # Debugging output

                # Use a regex to find and separate all complete JSON objects in the buffer
                buffer += response_json
                json_strings = re.findall(r'\{.*?\}(?=\{|\Z)', buffer)
                #print(f"Extracted JSON strings: {json_strings}")  # Debugging output
                
                # Convert each JSON string to a Python object
                response_objects = [json.loads(json_str) for json_str in json_strings]
                print(f"Response objects: {response_objects}")  # Debugging output

                return response_objects

        except Exception as e:
            print(f"Si è verificato un errore: {e}")
            return None
                          
request_data = {
    "action": {
        "getProperties": {
            "version": 512,
            "device": "Mount Simulator"            
             }
    }
}