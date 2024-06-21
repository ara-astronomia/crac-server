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
        root = self.__call(
            f"""
            <getProperties device="{self._name}"  version='2.0' name="MOUNT_EQUATORIAL_COORDINATES"/>  
            """
        )
        print(root)
        eq_coords = self.__retrieve_eq_coords(root)   
        logger.debug(f"data received from xml: {eq_coords}")     
        speed = self.__retrieve_speed(root)
        logger.debug(f"data received from xml: {speed}")
        aa_coords = self._retrieve_aa_coords(eq_coords)
        logger.debug(f"data received from xml: {aa_coords}")
        status = self._retrieve_status(aa_coords)
        logger.debug(f"data received from xml: {status}")

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
        for coords in root.findall("defNumber"):
            if coords.attrib["name"] == "RA":
                ra = round(float(coords.text), 2)
            elif coords.attrib["name"] == "DEC":
                dec = round(float(coords.text), 2)
        if ra and dec:
            return EquatorialCoords(ra=ra, dec=dec)
        else:
            raise Exception(f"RA or Dec not present. RA: {ra}, DEC: {dec}")

    def __call(self, script: str):
        self.s.sendall(script.encode('utf-8'))
        data = self.s.recv(30000).decode("utf-8")
        logger.debug(f"data received from xml: {data}")
        try:
            return ET.fromstring(data)
        except ET.ParseError as err:
            logger.error(f"Xml Malformed {err}")
            raise err

