import logging
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_protobuf.button_pb2 import ButtonKey
from crac_server.component.camera.camera import Camera as CameraBase
from pytapo import Tapo
import urllib


logger = logging.getLogger(__name__)


class Camera(CameraBase):
    def __init__(self, name: str, user: str, password: str, host: str, port = "554", source: str = None) -> None:
        self._tapo = Tapo(host, user, password)
        super().__init__(self.streamUrl(user, password, host, port, source), name)
        self._move = True
        self.refresh_status()
    
    def open(self):
        self._tapo.setPrivacyMode(False)
        super().open()
    
    def close(self):
        self._tapo.setPrivacyMode(True)
        super().close()
    
    @property
    def tapo(self):
        return self._tapo

    @property
    def can_move(self):
        return self._move
    
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
    
    def supported_features(self, key: str) -> list[ButtonKey]:
        supported = []
        if key == "camera1" and self._streaming:
            supported.append(ButtonKey.KEY_CAMERA1_DISPLAY)
        elif key == "camera2" and self._streaming:
            supported.append(ButtonKey.KEY_CAMERA2_DISPLAY)

        supported.extend(
            (
                ButtonKey.KEY_CAMERA_MOVE_UP,
                ButtonKey.KEY_CAMERA_MOVE_TOP_RIGHT,
                ButtonKey.KEY_CAMERA_MOVE_RIGHT,
                ButtonKey.KEY_CAMERA_MOVE_BOTTOM_RIGHT,
                ButtonKey.KEY_CAMERA_MOVE_DOWN,
                ButtonKey.KEY_CAMERA_MOVE_BOTTOM_LEFT,
                ButtonKey.KEY_CAMERA_MOVE_LEFT,
                ButtonKey.KEY_CAMERA_MOVE_TOP_LEFT,
                ButtonKey.KEY_CAMERA_IR_TOGGLE,
            )
        )

        return supported
