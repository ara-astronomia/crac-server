from datetime import datetime
from typing import Any
from crac_protobuf.telescope_pb2 import (
    EquatorialCoords,
    AltazimutalCoords,
    TelescopeSpeed,
    TelescopeStatus,  # type: ignore
)
from crac_server import config
from crac_server.component.telescope.telescope import Telescope as TelescopeBase
import logging
import json
import re
import os
import time
import socket
import sys, errno
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
                        {"newSwitchVector": 
                                { 
                                    "device": self._name, "name": "MOUNT_TRACKING", "state": "Ok", "items": 
                                    [
                                        { "name": "ON", "value": False}, 
                                        { "name": "OFF", "value": True} 
                                    ] 
                                } 
                            }
                        )
        else:
            self.__call(
                        {"newSwitchVector": 
                                { 
                                    "device": self._name, "name": "MOUNT_TRACKING", "state": "Ok", "items": 
                                    [
                                        { "name": "ON", "value": True}, 
                                        { "name": "OFF", "value": False} 
                                    ] 
                                } 
                            }
                        )
            
            if speed == TelescopeSpeed.SPEED_TRACKING:
                self.__call(
                            {"newNumberVector": 
                                { 
                                    "device": self._name, "name": "MOUNT_ON_COORDINATES_SET", "state": "Ok", "items": 
                                    [
                                        { "name": "SLEW", "value": True},
                                        { "name": "TRACK", "value": True}
                                    ] 
                                } 
                            }
                        )
            else:
                self.__call(
                            {"newNumberVector": 
                                { 
                                    "device": self._name, "name": "MOUNT_ON_COORDINATES_SET", "state": "Ok", "items": 
                                    [
                                        { "name": "SLEW", "value": False},
                                        { "name": "TRACK", "value": False},
                                        { "name": "SYNC", "value": False}

                                    ] 
                                } 
                            }
                        )


    def park(self, speed: TelescopeSpeed):
        self.__call(
                        {"newSwitchVector": 
                            { 
                                "device": self._name, "name": "MOUNT_PARK", "state": "Ok", "items": 
                                    [
                                        { "name": "PARKED", "value": True},
                                        { "name": "UNPARKED", "value": False}
                                    ] 
                            } 
                        }
                    )
                    
    def __retrieve_status_park(self, root):
        seen = set()
        
        for item in root:
            if "defSwitchVector" in item:
                vector = item["defSwitchVector"]
                if vector["name"] == "MOUNT_PARK":
                    for park in vector["items"]:
                        key = (vector["name"], vector['state'], park["name"], park["value"])
                        if key not in seen:
                            seen.add(key)
                            if park['name'] == "PARKED":
                                return park["value"] 

        return False
                           
    def flat(self, speed: TelescopeSpeed):
        speed=speed        
        self.__move(
                    aa_coords=AltazimutalCoords(
                        alt=config.Config.getFloat("flat_alt", "telescope"),
                        az=config.Config.getFloat("flat_az", "telescope")
                    ),
                speed=speed
                )
                
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            self.__call(
                            {"newSwitchVector": 
                                { 
                                    "device": self._name, "name": "MOUNT_TRACKING", "state": "Ok", "items": 
                                    [
                                        { "name": "ON", "value": False},
                                        { "name": "OFF", "value": True}
                                    ] 
                                } 
                            }
                        )

    def retrieve(self) -> tuple:
        root = self.__call(
                            {"getProperties": 
                                {
                                    "version": 512,
                                    "device": "Mount Simulator"
                                }
                            }
                        )
           
        
        eq_coords = self.__retrieve_eq_coords(root)   
        logger.debug(f"data received from json: {eq_coords}")     
        speed = self.__retrieve_speed(root)
        logger.debug(f"data received from json: {speed}")
        aa_coords = self._retrieve_aa_coords(eq_coords)
        logger.debug(f"data received from json: {aa_coords}")
        status = self._retrieve_status(aa_coords, root)
        logger.debug(f"data received from json: {status}")

        return (eq_coords, aa_coords, speed, status)
    
    def _retrieve_status(self, aa_coords: AltazimutalCoords, root: Any) -> TelescopeStatus:
        if not self._polling:
            return TelescopeStatus.DISCONNECTED
        elif self.__retrieve_status_park(root):
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

    def __move(self, aa_coords: AltazimutalCoords, speed=TelescopeSpeed.SPEED_TRACKING):
        self.__call(
                        {"newSwitchVector": 
                            { 
                                "device": self._name, "name": "MOUNT_PARK", "state": "Ok", "items": 
                                    [
                                        { "name": "PARKED", "value": False},
                                        { "name": "UNPARKED", "value": True}
                                    ] 
                            } 
                        }
                    )
        eq_coords = self._altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow()) if isinstance(aa_coords, (AltazimutalCoords)) else aa_coords
        logger.debug(aa_coords)
        logger.debug(eq_coords)
        self.queue_set_speed(speed)
        self.__call(
                    {"newNumberVector": 
                        { 
                            "device": self._name, "name": "MOUNT_EQUATORIAL_COORDINATES", "state": "Ok", "items": 
                            [
                                { "name": "DEC", "value": eq_coords.dec}, 
                                { "name": "RA", "value": eq_coords.ra} 
                            ] 
                        } 
                    }
                    )  
    def __retrieve_speed(self, root):
        seen = set()        
        for item in root:
            if "defSwitchVector" in item:
                vector = item["defSwitchVector"]
                if vector["name"] == "MOUNT_TRACKING":
                    for track in vector["items"]:
                        key = (vector["name"], vector['state'], track["name"], track["value"])
                        if key not in seen:
                            seen.add(key)
                            if track['name'] == "ON":
                                if track["value"] == True:
                                    status_mount_track = 'ON'
                                else:
                                    status_mount_track = 'OFF'    
                                
            if "defNumberVector" in item:
                vector = item["defNumberVector"]
                if vector["name"] == "MOUNT_EQUATORIAL_COORDINATES":
                    for coord in vector["items"]:
                        key = (vector["name"], vector['state'], coord["name"], coord["value"])
                        if key not in seen:
                            seen.add(key)
                            status_mount_speed= vector['state']
                                                        
                            if status_mount_speed == "Ok" and status_mount_track == 'ON':
                                return TelescopeSpeed.SPEED_TRACKING
                            if status_mount_speed == "Idle" and status_mount_track == 'OFF':
                                return TelescopeSpeed.SPEED_NOT_TRACKING
                            if status_mount_speed == "Busy":
                                return TelescopeSpeed.SPEED_SLEWING
                            else:
                                return TelescopeSpeed.SPEED_ERROR

                           
    def __retrieve_eq_coords(self, root):
        ra, dec = None, None
        seen = set()
        for item in root:            
            if "defNumberVector" in item:
                vector = item["defNumberVector"]
                if vector["name"] == "MOUNT_EQUATORIAL_COORDINATES":
                    for coord in vector["items"]:
                        key = (vector["name"], vector['state'], coord["name"], coord["value"])
                        if key not in seen:
                            seen.add(key)
                            if coord["name"] == "RA":
                                ra = round(float(coord['value']),5)
                            elif coord["name"] == "DEC":
                                dec = round(float(coord['value']),5)
        if ra and dec:
            return EquatorialCoords(ra=ra, dec=dec)
        else:
            raise Exception(f"RA or Dec not present. RA: {ra}, DEC: {dec}")
       
    def __call(self, script):
        request_json = json.dumps(script)
        self.s.settimeout(1)  # Set a timeout for the socket  
        responses=[]

        def send_and_receive(request):
            response=b""
            try:
                self.s.sendall(request)
                time.sleep(5)
                while True:
                    try:
                        part = self.s.recv(2500000)
                        if not part:
                            break
                        response +=part

                    except socket.timeout:
                        print("Socket timeout, stopping reception.")
                        break

                    return response        
            except Exception as e:
                if isinstance(e, socket.error) and e.errno == errno.EPIPE:
                    print(f"Si è verificato un errore: {e}")
            
        response_with_newline = send_and_receive(request_json.encode('utf-8') + b'\n')
        if response_with_newline:
            responses.append(response_with_newline.decode('utf-8'))


        # Send request without newline
        response_without_newline = send_and_receive(request_json.encode('utf-8'))
        if response_without_newline:
            responses.append(response_without_newline.decode('utf-8'))

        # Combine responses and process them
        combined_response = "\n".join(responses)  

        # Use a regex to find and separate all complete JSON objects in the combined response
        json_strings = re.findall(r'\{.*?\}(?=\{|\Z)', combined_response)

        # Convert each JSON string to a Python object
        response_objects = []
        for json_str in json_strings:
            try:
                json_obj = json.loads(json_str)
                response_objects.append(json_obj)
            except json.JSONDecodeError as e:
                print(f"Errore nella decodifica del JSON: {e}")
       
        return response_objects