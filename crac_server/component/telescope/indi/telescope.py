from datetime import datetime
import logging
import socket
from time import sleep
from crac_server import config
from crac_server.component.telescope.telescope import Telescope as BaseTelescope
from crac_protobuf.telescope_pb2 import (
    AltazimutalCoords,
    EquatorialCoords,
    TelescopeSpeed,
)
import xml.etree.ElementTree as ET


logger = logging.getLogger(__name__)


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

    def __call_indi__(self, script: str, **kwargs) -> bytes:
        self.open_connection()
        self.s.sendall(script.encode('utf-8'))
        data = self.s.recv(30000)
        print(data)
        self.disconnect()
        return ET.fromstring(data)


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
        eq_coords = self.__altaz2radec(aa_coords)
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

    def move(self, aa_coords: AltazimutalCoords | EquatorialCoords, speed=TelescopeSpeed.TRACKING):
        self.__call_indi__(
            """
                <newSwitchVector device="Telescope Simulator" name="TELESCOPE_PARK">
                    <oneSwitch name="UNPARK">
                        On
                    </oneSwitch>
                </newSwitchVector>
            """
        )
        eq_coords = self.__altaz2radec(aa_coords) if isinstance(aa_coords, (AltazimutalCoords)) else aa_coords
        print(aa_coords)
        print(eq_coords)
        print(self.__radec2altaz(eq_coords))

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
        if speed is TelescopeSpeed.DEFAULT:
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
                            {"On" if speed == TelescopeSpeed.SLEWING else "Off"}
                        </oneSwitch>
                        <oneSwitch name="TRACK">
                            {"On" if speed == TelescopeSpeed.TRACKING else "Off"}
                        </oneSwitch>
                        <oneSwitch name="SYNC">
                            Off
                        </oneSwitch>
                    </newSwitchVector>
                """
            )

    def get_aa_coords(self):
        eq_coords = self.get_eq_coords()
        return self.__radec2altaz(eq_coords)

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

        return EquatorialCoords(ra=ra, dec=dec)

    def get_speed(self):
        root = self.__call_indi__(
            """
            <getProperties device="Telescope Simulator" version="1.7" name="TELESCOPE_TRACK_STATE"/>
            """
        )
        for switch in root.findall("defSwitch"):
            if switch.attrib["name"] == "TRACK_ON":
                track_on = switch.text.strip()
            elif switch.attrib["name"] == "TRACK_OFF":
                track_off = switch.text.strip()

        if track_on == "Off" or track_off == "On":
            return TelescopeSpeed.DEFAULT

        root = self.__call_indi__(
            """
            <getProperties device="Telescope Simulator" version="1.7" name="ON_COORD_SET"/>
            """
        )
        for switch in root.findall("defSwitch"):
            if switch.attrib["name"] == "TRACK":
                track = switch.text.strip()
            elif switch.attrib["name"] == "SLEW":
                slew = switch.text.strip()

        if track == "On":
            return TelescopeSpeed.TRACKING
        elif slew == "On":
            return TelescopeSpeed.SLEWING

    def park(self, speed=TelescopeSpeed.DEFAULT):
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

    def flat(self, speed=TelescopeSpeed.DEFAULT):
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

TELESCOPE = Telescope()

if __name__ == '__main__':
    t = Telescope()
    t.port = 7624
    t.hostname = "localhost"
    #t.park()
    # sleep(5)
    # t.flat()
    # t.move(
    #     aa_coords=AltazimutalCoords(
    #         alt=config.Config.getFloat("park_alt", "telescope"),
    #         az=config.Config.getFloat("park_az", "telescope")
    #     )
    # )
    #t.flat()
    #t.sync()
    #print(t.get_eq_coords())
    #print(t.get_aa_coords())
    t.set_speed(TelescopeSpeed.DEFAULT)
    print(t.get_speed())
    sleep(5)
    t.set_speed(TelescopeSpeed.TRACKING)
    print(t.get_speed())
    sleep(5)
    t.set_speed(TelescopeSpeed.SLEWING)
    print(t.get_speed())