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

logger = logging.getLogger(__name__)


class Telescope(TelescopeBase):

    # default port 7624
    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        super().__init__(hostname=hostname, port=port)
        self._name = config.Config.getValue("name", "indigo")
        logger.debug(f"Mount type: {self._name}")

    def sync(self, started_at: datetime):
        self.__call(
            f"""
                <newSwitchVector client="{self._name}" name="MOUNT_ON_COORDINATES_SET">
                    <oneSwitch name="SLEW">
                        OFF
                    </oneSwitch>
                    <oneSwitch name="TRACK">
                        OFF
                    </oneSwitch>
                    <oneSwitch name="SYNC">
                        ON
                    </oneSwitch>
                </newSwitchVector>
            """
        )
        eq_coords = self._calculate_eq_coords_of_park_position(started_at)
        self.__call(
            f"""
                <newNumberVector client="{self._name}" name="MOUNT_EQUATORIAL_COORDINATES">
                    <oneNumber name="DEC">
                      {eq_coords.dec}
                    </oneNumber>
                    <oneNumber name="RA">
                      {eq_coords.ra}
                    </oneNumber>
                </newNumberVector>
            """
        )
        self.__call(
            f"""
                <newSwitchVector client="{self._name}" name="MOUNT_ON_COORDINATES_SET">
                    <oneSwitch name="SLEW">
                        OFF
                    </oneSwitch>
                    <oneSwitch name="TRACK">
                        ON
                    </oneSwitch>
                    <oneSwitch name="SYNC">
                        OFF
                    </oneSwitch>
                </newSwitchVector>
            """
        )

    def set_speed(self, speed: TelescopeSpeed):
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            self.__call(
                f"""
                    <newSwitchVector client="{self._name}" name="MOUNT_TRACKING">
                        <oneSwitch name="OFF">
                            ON
                        </oneSwitch>
                    </newSwitchVector>
                """
            )
        else:
            self.__call(
                f"""
                    <newSwitchVector client="{self._name}" name="MOUNT_TRACKING">
                        <oneSwitch name="ON">
                            ON
                        </oneSwitch>
                    </newSwitchVector>
                """
            )
            self.__call(
                f"""
                    <newSwitchVector client="{self._name}" name="MOUNT_ON_COORDINATES_SET">
                        <oneSwitch name="SLEW">
                            {"ON" if speed == TelescopeSpeed.SPEED_SLEWING else "OFF"}
                        </oneSwitch>
                        <oneSwitch name="TRACK">
                            {"ON" if speed == TelescopeSpeed.SPEED_TRACKING else "OFF"}
                        </oneSwitch>
                        <oneSwitch name="SYNC">
                            OFF
                        </oneSwitch>
                    </newSwitchVector>
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
                <newSwitchVector client="{self._name}" name="MOUNT_TRACKING">
                    <oneSwitch name="OFF">
                        ON
                    </oneSwitch>
                </newSwitchVector>
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
                <newSwitchVector client="{self._name}" name="MOUNT_TRACKING">
                    <oneSwitch name="OFF">
                        ON
                    </oneSwitch>
                </newSwitchVector>
                """
            )

    def retrieve(self) -> tuple:
        root = self.__call(
            f"""
            { "getProperties": { "version": 512, "client": "{self._name}", name="MOUNT_EQUATORIAL_COORDINATES" } }
            """
        )
        eq_coords = self.__retrieve_eq_coords(root)
        speed = self.__retrieve_speed(root)
        aa_coords = self._retrieve_aa_coords(eq_coords)
        status = self._retrieve_status(aa_coords)
        return (eq_coords, aa_coords, speed, status)

    def __move(self, aa_coords: AltazimutalCoords, speed=TelescopeSpeed.SPEED_TRACKING):
        self.__call(
            f"""
                <newSwitchVector client="{self._name}" name="MOUNT_PARK">
                    <oneSwitch name="UNPARKED">
                        ON
                    </oneSwitch>
                </newSwitchVector>
            """
        )
        eq_coords = self._altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow()) if isinstance(aa_coords, (AltazimutalCoords)) else aa_coords
        logger.debug(aa_coords)
        logger.debug(eq_coords)
        self.queue_set_speed(speed)
        self.__call(
            f"""
                <newNumberVector client="{self._name}" name="MOUNT_EQUATORIAL_COORDINATES">
                    <oneNumber name="DEC">
                      {eq_coords.dec}
                    </oneNumber>
                    <oneNumber name="RA">
                      {eq_coords.ra}
                    </oneNumber>
                </newNumberVector>
            """
        )

    def __retrieve_speed(self, root):
        state = root.attrib["state"].strip() if root else None
        if state == "OK":
            return TelescopeSpeed.SPEED_TRACKING
        elif state == "IDLE":
            return TelescopeSpeed.SPEED_NOT_TRACKING
        elif state == "BUSY":
            return TelescopeSpeed.SPEED_SLEWING
        else:
            return TelescopeSpeed.SPEED_ERROR
   
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
            raise Exception(f"RA or DEC not present. RA: {ra}, DEC: {dec}")

    def __call(self, script: str):
        data = script
        properties=json.loads(data)
        logger.debug(properties)
        try:
            return properties
        except :
            logger.error(f"properties not found")