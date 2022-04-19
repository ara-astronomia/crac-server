from abc import ABC, abstractmethod
import logging
import urllib

from numpy import empty
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_protobuf.button_pb2 import ButtonKey
from crac_server.component.camera.streaming import Streaming

logger = logging.getLogger(__name__)


class Camera(ABC):

    def __init__(self, name: str, source: str, streaming: bool = True, settings: bool = True) -> None:
        self._name = name
        logger.debug(f"streaming in CameraBase is {streaming}")
        self._streaming = Streaming(source, name) if streaming else None
        self._settings = settings
        self._status = CameraStatus.CAMERA_HIDDEN
        self.ir = 0

    @property
    def status(self):
        return self._status
    
    @property
    def name(self):
        return self._name

    @property
    def is_hidden(self):
        return True if self._status is CameraStatus.CAMERA_HIDDEN else False
    
    @abstractmethod
    def ir(self, mode: int):
        """ 
            Let the cam to turn of ir if needed 
            0 - off
            1 - on
            2 - auto

            when off, the ir is never turned on
            when on, the ir is always used
            when auto, the ir is enabled by the camera itself
        """

    def streamUrl(self, user: str, password: str, host: str, port: str, stream: str):
        return f"rtsp://{urllib.parse.quote_plus(user)}:{urllib.parse.quote_plus(password)}@{host}:{port}/{stream}"
    
    def read(self):
        """ Read the streaming frame by frame """

        if self.status is CameraStatus.CAMERA_SHOWN:
            return self._streaming.read()
        else:
            return (True, self._streaming._black_frame)

    def close(self):
        self._streaming.close()
        self._status = CameraStatus.CAMERA_DISCONNECTED

    def open(self):
        if self._streaming.open():
            self._status = CameraStatus.CAMERA_HIDDEN

    def show(self):
        if self._status is not CameraStatus.CAMERA_DISCONNECTED:
            self._status = CameraStatus.CAMERA_SHOWN

    def hide(self):
        if self._status is not CameraStatus.CAMERA_DISCONNECTED:
            self._status = CameraStatus.CAMERA_HIDDEN

    @abstractmethod
    def move_top_left(self):
        """ Move camera top left """

    @abstractmethod
    def move_up(self):
        """ Move camera up """
    
    @abstractmethod
    def move_top_right(self):
        """ Move camera top right """

    @abstractmethod
    def move_right(self):
        """ Move camera right """

    @abstractmethod
    def move_bottom_right(self):
        """ Move camera top left """
    
    @abstractmethod
    def move_down(self):
        """ Move camera bottom """

    @abstractmethod
    def move_bottom_left(self):
        """ Move camera top left """

    @abstractmethod
    def move_left(self):
        """ Move camera left """

    @abstractmethod
    def stop(self):
        """ Stop camera """

    def supported_features(self, key: str) -> list[ButtonKey]:
        """ List of supported features """

        supported = []
        supported.extend(self._base_supported_features(key))

        if self._settings:
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
                )
            )

        return supported

    def _base_supported_features(self, key: str) -> list[ButtonKey]:
        supported = []
        if key == "camera1":
            if self._streaming:
                supported.extend(
                    (
                        ButtonKey.KEY_CAMERA1_CONNECTION,
                        ButtonKey.KEY_CAMERA1_DISPLAY,
                    )
                )
            if self._settings:
                supported.append(ButtonKey.KEY_CAMERA1_IR_TOGGLE)
        elif key == "camera2": 
            if self._streaming:
                supported.extend(
                    (
                        ButtonKey.KEY_CAMERA2_CONNECTION,
                        ButtonKey.KEY_CAMERA2_DISPLAY,
                    )
                )
            if self._settings:
                supported.append(ButtonKey.KEY_CAMERA2_IR_TOGGLE)
        return supported
