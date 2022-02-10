from configparser import ConfigParser
import datetime
import os
from crac_server.component.telescope.telescope import Telescope as BaseTelescope
from crac_protobuf.telescope_pb2 import (
    AltazimutalCoords,
    EquatorialCoords,
    TelescopeSpeed,
)
from crac_server.config import Config


class Telescope(BaseTelescope):
    def __init__(self):
        super().__init__()

    def disconnect(self) -> bool:
        return True

    def move(self, aa_coords: AltazimutalCoords, speed: TelescopeSpeed):
        if speed == TelescopeSpeed.TRACKING:
            sl = 1
            tr = 0
        elif speed == TelescopeSpeed.SLEWING:
            sl = 0
            tr = 1
        else:
            sl = 1
            tr = 1
        telescope_config = ConfigParser()
        telescope_config["coords"] = {'alt': str(aa_coords.alt), 'az': str(aa_coords.az), 'tr': str(tr), 'sl': str(sl), 'error': 0}
        telescope_path = os.path.join(os.path.dirname(__file__), 'telescope.ini')
        with open(telescope_path, 'w') as telescope_file:
            telescope_config.write(telescope_file)

    def sync(self):
        """ 
            Register the telescope in park position
            Calculate the corrisponding equatorial coordinate
        """
        self.sync_time = datetime.datetime.utcnow()
        aa_coords = AltazimutalCoords(
            alt=Config.getFloat("park_alt", "telescope"),
            az=Config.getFloat("park_az", "telescope")
        )
        telescope_config = ConfigParser()
        telescope_config["coords"] = {'alt': str(aa_coords.alt), 'az': str(aa_coords.az), 'tr': 1, 'sl': 1, 'error': 0}
        telescope_path = os.path.join(os.path.dirname(__file__), 'telescope.ini')
        with open(telescope_path, 'w') as telescope_file:
            telescope_config.write(telescope_file)
        self.sync_status = True

    def nosync(self):
        self.sync_time = None
        self.sync_status = False
    
    def get_aa_coords(self) -> AltazimutalCoords:
        telescope_path = os.path.join(os.path.dirname(__file__), 'telescope.ini')
        telescope_config = ConfigParser()
        telescope_config.read(telescope_path)
        alt = telescope_config.get("coords", "alt", fallback=0)
        az = telescope_config.get("coords", "az", fallback=0)
        return AltazimutalCoords(alt=float(alt), az=float(az))

    def get_eq_coords(self) -> EquatorialCoords:
        aa_coords = self.get_aa_coords()
        return self.__altaz2radec(aa_coords)

    def get_speed(self) -> TelescopeSpeed:
        telescope_path = os.path.join(os.path.dirname(__file__), 'telescope.ini')
        telescope_config = ConfigParser()
        telescope_config.read(telescope_path)
        tr = telescope_config.get("coords", "tr", fallback=0)
        sl = telescope_config.get("coords", "sl", fallback=1)
        if tr == "1" and sl == "1":
            return TelescopeSpeed.DEFAULT
        elif tr == "0" and sl == "1":
            return TelescopeSpeed.TRACKING
        elif tr == "1" and sl == "0":
            return TelescopeSpeed.SLEWING


TELESCOPE = Telescope()