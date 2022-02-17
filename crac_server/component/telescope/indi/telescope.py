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
    def __init__(self):
        self.sync_time = None
        self.sync_status = False
        self.connected = False
    
    def open_connection(self) -> None:

        if not self.connected:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.connect((self.hostname, self.port))
            self.connected = True

    def __call_indi__(self, script: str, **kwargs) -> bytes:
        self.open_connection()
        # with open(script, 'r') as p:
        #     file = p.read()
        #     if kwargs:
        #         if kwargs.get("az") is None:
        #             kwargs["az"] = ""
        #         if kwargs.get("alt") is None:
        #             kwargs["alt"] = ""
        #         file = file.format(**kwargs)
        self.s.sendall(script.encode('utf-8'))
        data = self.s.recv(30000)
        #logger.debug("Data received from xml: %s", data)
        print(data)
        #print(ET.fromstring(data))
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
        #self.indi
    
    def nosync(self):
        """ 
            Unregister the telescope
        """
        raise NotImplementedError()

    def move(self, aa_coords: AltazimutalCoords, speed=TelescopeSpeed.SLEWING):
        self.__call_indi__(
            """
                <newSwitchVector device="Telescope Simulator" name="TELESCOPE_PARK">
                    <oneSwitch name="UNPARK">
                        On
                    </oneSwitch>
                </newSwitchVector>
            """
        )
        self.__call_indi__(
            f"""
                <newNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD">
                    <oneNumber name="ALT">
                {aa_coords.alt}
                    </oneNumber>
                    <oneNumber name="AZ">
                {aa_coords.az}
                    </oneNumber>
                </newNumberVector>

            """)
    
    def set_speed(self, speed: TelescopeSpeed):
        raise NotImplementedError()

    def get_aa_coords(self):
        raise NotImplementedError()

    def get_eq_coords(self):
        raise NotImplementedError()

    def get_speed(self):
        raise NotImplementedError()

    def park(self, speed=TelescopeSpeed.DEFAULT):
        print("in park")
        self.__call_indi__(
            f"""
                <newNumberVector device="Telescope Simulator" name="TELESCOPE_PARK_POSITION">
                    <oneNumber name="PARK_ALT">
                        {config.Config.getFloat("park_alt", "telescope")}
                    </oneNumber>
                    <oneNumber name="PARK_AZ">
                        {config.Config.getFloat("park_az", "telescope")}
                    </oneNumber>
                </newNumberVector>
            """
        )
        self.__call_indi__(
            """
                <newSwitchVector device="Telescope Simulator" name="TELESCOPE_PARK_OPTION">
                    <oneSwitch name="PARK_WRITE_DATA">
                        On
                    </oneSwitch>
                </newSwitchVector>
            """
        )
        self.__call_indi__(
            """
                <newSwitchVector device="Telescope Simulator" name="TELESCOPE_PARK">
                    <oneSwitch name="PARK">
                        On
                    </oneSwitch>
                </newSwitchVector>
            """
        )

    def flat(self, speed=TelescopeSpeed.DEFAULT):
        print("in flat")
        self.move(
            aa_coords=AltazimutalCoords(
                alt=config.Config.getFloat("flat_alt", "telescope"),
                az=config.Config.getFloat("flat_az", "telescope")
            ),
            speed=speed
        )

if __name__ == '__main__':
    t = Telescope()
    t.port = 7624
    t.hostname = "localhost"
    t.park()
    # sleep(5)
    # t.flat()