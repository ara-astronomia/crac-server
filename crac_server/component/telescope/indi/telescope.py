import logging
from crac_server import config
from crac_server.component.telescope.telescope import Telescope as BaseTelescope
from crac_protobuf.telescope_pb2 import (
    AltazimutalCoords,
    EquatorialCoords,
    TelescopeSpeed,
)
from datetime import datetime
import socket
import threading 
from time import sleep
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)
lock = threading.Lock()


class Telescope(BaseTelescope):
    def __init__(self, hostname="localhost", port=7624):
        self.sync_time = None
        self.sync_status = False
        self.connected = False
        self.hostname = hostname
        self.port = port
    
    def open_connection(self) -> None:

        if not self.connected:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.connect((self.hostname, self.port))
            self.connected = True

    def __call_indi__(self, script: str) -> bytes:
        with lock:
            self.open_connection()
            self.s.sendall(script.encode('utf-8'))
            data = self.s.recv(30000)
            self.disconnect()
            logger.debug(data)
        try:
            return ET.fromstring(data)
        except ET.ParseError as err:
            logger.error(f"Xml Malformed {err}")


    def disconnect(self) -> bool:
        """ Disconnect the server from the Telescope"""
        if self.connected:
            self.s.close()
            self.connected = False

    def sync(self):
        """ 
            Register the telescope in park position
            Calculate the corrisponding equatorial coordinate
        """
        self.sync_time = datetime.utcnow()
        self.__call_indi__(
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
        eq_coords = self.__altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow())
        self.__call_indi__(
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
        self.__call_indi__(
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
        self.sync_status = True

    def move(self, aa_coords: AltazimutalCoords, speed=TelescopeSpeed.SPEED_TRACKING):
        self.__call_indi__(
            """
                <newSwitchVector device="Telescope Simulator" name="TELESCOPE_PARK">
                    <oneSwitch name="UNPARK">
                        On
                    </oneSwitch>
                </newSwitchVector>
            """
        )
        eq_coords = self.__altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow()) if isinstance(aa_coords, (AltazimutalCoords)) else aa_coords
        logger.debug(aa_coords)
        logger.debug(eq_coords)
        logger.debug(self.__radec2altaz(eq_coords, obstime=datetime.utcnow()))
        self.set_speed(speed)
        self.__call_indi__(
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
    
    def set_speed(self, speed: TelescopeSpeed):
        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            self.__call_indi__(
                """
                    <newSwitchVector device="Telescope Simulator" name="TELESCOPE_TRACK_STATE">
                        <oneSwitch name="TRACK_OFF">
                            On
                        </oneSwitch>
                    </newSwitchVector>
                """
            )
        else:
            self.__call_indi__(
                """
                    <newSwitchVector device="Telescope Simulator" name="TELESCOPE_TRACK_STATE">
                        <oneSwitch name="TRACK_ON">
                            On
                        </oneSwitch>
                    </newSwitchVector>
                """
            )
            self.__call_indi__(
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

    def get_aa_coords(self):
        eq_coords = self.get_eq_coords()
        aa_coords = self.__radec2altaz(eq_coords, obstime=datetime.utcnow())
        logger.debug(f"Coordinate altazimutali {aa_coords}")
        logger.debug(f"Riconversione in coordinate equatoriali {self.__altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow())}")
        return aa_coords

    def get_eq_coords(self):
        root = self.__call_indi__(
            """
            <getProperties device="Telescope Simulator" version="1.7" name="EQUATORIAL_EOD_COORD"/>
            """
        )

        for coords in root.findall("defNumber"):
            if coords.attrib["name"] == "RA":
                ra = round(float(coords.text), 2)
            elif coords.attrib["name"] == "DEC":
                dec = round(float(coords.text), 2)

        eq_coords = EquatorialCoords(ra=ra, dec=dec)
        logger.debug(f"Coordinate equatoriali {eq_coords}")
        return eq_coords

    def get_speed(self):
        root = self.__call_indi__(
            """
            <getProperties device="Telescope Simulator" version="1.7" name="EQUATORIAL_EOD_COORD"/>
            """
        )
        state = root.attrib["state"].strip()

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

    def park(self, speed=TelescopeSpeed.SPEED_NOT_TRACKING):
        self.move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("park_alt", "telescope"),
                az=config.Config.getFloat("park_az", "telescope")
            ),
            speed=speed
        )
        self.__call_indi__(
            """
            <newSwitchVector device="Telescope Simulator" name="TELESCOPE_TRACK_STATE">
                <oneSwitch name="TRACK_OFF">
                    On
                </oneSwitch>
            </newSwitchVector>
            """
        )

    def flat(self, speed=TelescopeSpeed.SPEED_NOT_TRACKING):
        self.move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("flat_alt", "telescope"),
                az=config.Config.getFloat("flat_az", "telescope")
            ),
            speed=speed
        )
        self.__call_indi__(
            """
            <newSwitchVector device="Telescope Simulator" name="TELESCOPE_TRACK_STATE">
                <oneSwitch name="TRACK_OFF">
                    On
                </oneSwitch>
            </newSwitchVector>
            """
        )

TELESCOPE = Telescope(hostname=config.Config.getValue('hostname', 'telescope'), port=config.Config.getInt('port', 'telescope'))


if __name__ == '__main__':
    t = Telescope()
    t.port = 7624
    t.hostname = "localhost"
    # #t.park()
    # # sleep(5)
    # # t.flat()
    # # t.move(
    # #     aa_coords=AltazimutalCoords(
    # #         alt=config.Config.getFloat("park_alt", "telescope"),
    # #         az=config.Config.getFloat("park_az", "telescope")
    # #     )
    # # )
    # #t.flat()
    # #t.sync()
    # #print(t.get_eq_coords())
    # #print(t.get_aa_coords())
    # t.set_speed(TelescopeSpeed.SPEED_NOT_TRACKING)
    # print(t.get_speed())
    # sleep(5)
    # t.set_speed(TelescopeSpeed.SPEED_TRACKING)
    # print(t.get_speed())
    # sleep(5)
    # t.set_speed(TelescopeSpeed.SPEED_SLEWING)
    print(t.get_speed())


    # from skyfield.api import N, Star, W, wgs84, load, wgs84
    # position = wgs84.latlon(latitude_degrees=42.22933, longitude_degrees=12.8115, elevation_m=465)
    # ts = load.timescale()
    # time = ts.utc(2022, 2, 18, 10, 2, 40)
    # planets = load('de421.bsp')
    # earth = planets['earth']
    # observatory = earth + position
    # gc = Star(ra_hours=(6, 52, 19.95), dec_degrees=(41, 45, 20.54))
    # observation = observatory.at(time).observe(gc)
    # aa_coords = observation.apparent().altaz()
    # print(aa_coords)
    # print(t.get_aa_coords())
    # print(t.get_eq_coords())