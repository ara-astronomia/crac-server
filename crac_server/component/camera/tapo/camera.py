from distutils.util import strtobool
import logging
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_protobuf.button_pb2 import ButtonKey
from crac_server.component.camera.camera import Camera as CameraBase
from pytapo import Tapo


logger = logging.getLogger(__name__)


class Camera(CameraBase):
    def __init__(self, name: str, source: str, user: str, password: str, host: str, port = "554", streaming: str = "True", settings: str = "True") -> None:
        self._tapo = Tapo(host, user, password) if strtobool(settings) else None
        super().__init__(source=self.streamUrl(user, password, host, port, source), name=name, streaming=strtobool(streaming), settings=strtobool(settings))
        logger.debug(f"streaming is {self._streaming}")
        logger.debug(f"settings is {self._settings}")
        self.refresh_status()
    
    def open(self):
        if self._settings:
            self._tapo.setPrivacyMode(False)
            super().open()
    
    def close(self):
        if self._settings:
            self._tapo.setPrivacyMode(True)
            super().close()
    
    @property
    def tapo(self):
        return self._tapo
    
    def refresh_status(self):
        if self.is_hidden:
            self._status = CameraStatus.CAMERA_HIDDEN
        else:
            self._status = CameraStatus.CAMERA_SHOWN

    def move_top_left(self):
        self.__ptz("UP")
        self.__ptz(pan="LEFT")

    def move_up(self):
        self.__ptz("UP")

    def move_top_right(self):
        self.__ptz("UP")
        self.__ptz(pan="RIGHT")

    def move_right(self):
        self.__ptz(pan="RIGHT")

    def move_bottom_right(self):
        self.__ptz("BOTTOM")
        self.__ptz(pan="RIGHT")
    
    def move_down(self):
        self.__ptz("BOTTOM")

    def move_bottom_left(self):
        self.__ptz("BOTTOM")
        self.__ptz(pan="LEFT")

    def move_left(self):
        self.__ptz(pan="LEFT")

    def stop(self):
        raise NotImplementedError()
    
    @property
    def ir(self):
        return self._ir
    
    @ir.setter
    def ir(self, mode: int):
        if not self._settings:
            self._ir = 0
            return

        logger.debug(f"Setting ir mode on foscam: {mode}")
        if mode == 0:
            inf_type = "off"
        elif mode == 1:
            inf_type = "on"
        elif mode == 2:
            inf_type = "auto"
        else:
            raise Exception("Invalid inf_type, can be off, on or auto")
        
        self._tapo.setDayNightMode(inf_type)
        
        self._ir = mode

    def __ptz(self, tilt=None, pan=None, preset=None, distance=None):
        if preset:
            if preset.isnumeric():
                self._tapo.setPreset(preset)
            else:
                foundKey = False
                for key, value in self._attributes["presets"].items():
                    if value == preset:
                        foundKey = key
                if foundKey:
                    self._tapo.setPreset(foundKey)
                else:
                    logger.error("Preset " + preset + " does not exist.")
        elif tilt:
            if distance:
                distance = float(distance)
                if distance >= 0 and distance <= 1:
                    degrees = 68 * distance
                else:
                    degrees = 5
            else:
                degrees = 5
            if tilt == "UP":
                self._tapo.moveMotor(0, degrees)
            else:
                self._tapo.moveMotor(0, -degrees)
        elif pan:
            if distance:
                distance = float(distance)
                if distance >= 0 and distance <= 1:
                    degrees = 360 * distance
                else:
                    degrees = 5
            else:
                degrees = 5
            if pan == "RIGHT":
                self._tapo.moveMotor(degrees, 0)
            else:
                self._tapo.moveMotor(-degrees, 0)
        else:
            logger.error(
                """
                    Incorrect additional PTZ properties.
                    You need to specify at least one of
                    tilt,
                    pan,
                    preset,
                """
            )
