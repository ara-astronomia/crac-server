from datetime import datetime
from crac_protobuf.telescope_pb2 import (
    EquatorialCoords,
    AltazimutalCoords,
    TelescopeSpeed,
)
from crac_server import config
from crac_server.component.telescope.telescope import Telescope as TelescopeBase
import logging
import xml.etree.ElementTree as ET


logger = logging.getLogger(__name__)


class Telescope(TelescopeBase):

    # default port 7624
    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        super().__init__(hostname=hostname, port=port)

    def sync(self):
        self.sync_time = datetime.utcnow()
        self.__call(
            """
                <newSwitchVector device="Telescope Simulator" name="ON_COORD_SET">
                    <oneSwitch name="SLEW">
                        Off
                    </oneSwitch>
                    <oneSwitch name="TRACK">
                        Off
                    </oneSwitch>
                    <oneSwitch name="SYNC">
                        On
                    </oneSwitch>
                </newSwitchVector>
            """
        )
        aa_coords = AltazimutalCoords(
            alt=config.Config.getFloat("park_alt", "telescope"),
            az=config.Config.getFloat("park_az", "telescope")
        )
        eq_coords = self._altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow())
        self.__call(
            f"""
                <newNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD">
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
            """
                <newSwitchVector device="Telescope Simulator" name="ON_COORD_SET">
                    <oneSwitch name="SLEW">
                        Off
                    </oneSwitch>
                    <oneSwitch name="TRACK">
                        On
                    </oneSwitch>
                    <oneSwitch name="SYNC">
                        Off
                    </oneSwitch>
                </newSwitchVector>
            """
        )

    def set_speed(self, speed: TelescopeSpeed):
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            self.__call(
                """
                    <newSwitchVector device="Telescope Simulator" name="TELESCOPE_TRACK_STATE">
                        <oneSwitch name="TRACK_OFF">
                            On
                        </oneSwitch>
                    </newSwitchVector>
                """
            )
        else:
            self.__call(
                """
                    <newSwitchVector device="Telescope Simulator" name="TELESCOPE_TRACK_STATE">
                        <oneSwitch name="TRACK_ON">
                            On
                        </oneSwitch>
                    </newSwitchVector>
                """
            )
            self.__call(
                f"""
                    <newSwitchVector device="Telescope Simulator" name="ON_COORD_SET">
                        <oneSwitch name="SLEW">
                            {"On" if speed == TelescopeSpeed.SPEED_SLEWING else "Off"}
                        </oneSwitch>
                        <oneSwitch name="TRACK">
                            {"On" if speed == TelescopeSpeed.SPEED_TRACKING else "Off"}
                        </oneSwitch>
                        <oneSwitch name="SYNC">
                            Off
                        </oneSwitch>
                    </newSwitchVector>
                """
            )

    def park(self, speed=TelescopeSpeed.SPEED_NOT_TRACKING):
        self.__move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("park_alt", "telescope"),
                az=config.Config.getFloat("park_az", "telescope")
            ),
            speed=speed
        )
        self.__call(
            """
            <newSwitchVector device="Telescope Simulator" name="TELESCOPE_TRACK_STATE">
                <oneSwitch name="TRACK_OFF">
                    On
                </oneSwitch>
            </newSwitchVector>
            """
        )

    def flat(self, speed=TelescopeSpeed.SPEED_NOT_TRACKING):
        self.__move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("flat_alt", "telescope"),
                az=config.Config.getFloat("flat_az", "telescope")
            ),
            speed=speed
        )
        self.__call(
            """
            <newSwitchVector device="Telescope Simulator" name="TELESCOPE_TRACK_STATE">
                <oneSwitch name="TRACK_OFF">
                    On
                </oneSwitch>
            </newSwitchVector>
            """
        )

    def retrieve(self) -> tuple:
        root = self.__call(
            """
            <getProperties device="Telescope Simulator" version="1.7" name="EQUATORIAL_EOD_COORD"/>
            """
        )
        eq_coords = self.__retrieve_eq_coords(root)
        speed = self.__retrieve_speed(root)
        aa_coords = self._retrieve_aa_coords(eq_coords)
        status = self._retrieve_status(aa_coords)

        return (eq_coords, aa_coords, speed, status)

    def __move(self, aa_coords: AltazimutalCoords, speed=TelescopeSpeed.SPEED_TRACKING):
        self.__call(
            """
                <newSwitchVector device="Telescope Simulator" name="TELESCOPE_PARK">
                    <oneSwitch name="UNPARK">
                        On
                    </oneSwitch>
                </newSwitchVector>
            """
        )
        eq_coords = self._altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow()) if isinstance(aa_coords, (AltazimutalCoords)) else aa_coords
        logger.debug(aa_coords)
        logger.debug(eq_coords)
        logger.debug(self._radec2altaz(eq_coords, obstime=datetime.utcnow()))
        self.queue_set_speed(speed)
        self.__call(
            f"""
                <newNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD">
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
        for coords in root.findall("defNumber"):
            if coords.attrib["name"] == "RA":
                ra = round(float(coords.text), 2)
            elif coords.attrib["name"] == "DEC":
                dec = round(float(coords.text), 2)

        return EquatorialCoords(ra=ra, dec=dec)

    def __call(self, script: str):
        self.s.sendall(script.encode('utf-8'))
        data = self.s.recv(30000)
        logger.debug(data)
        try:
            return ET.fromstring(data)
        except ET.ParseError as err:
            logger.error(f"Xml Malformed {err}")
            raise err

TELESCOPE = Telescope()

# while True:
#     print(TELESCOPE.aa_coords)
#     print(TELESCOPE.eq_coords)
#     if TELESCOPE.speed:
#         print(TelescopeSpeed.Name(TELESCOPE.speed))
#     if TELESCOPE.status:
#         print(TelescopeStatus.Name(TELESCOPE.status))
#     sleep(2)