from abc import ABC, abstractmethod
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_protobuf.button_pb2 import ButtonKey
from crac_server.component.camera.streaming import Streaming


class Camera(ABC):

    def __init__(self, source: str, name: str) -> None:
        self._name = name
        if source:
            self._streaming = Streaming(source, name)
        self._status = CameraStatus.CAMERA_HIDDEN

    @property
    def status(self):
        return self._status
    
    @property
    def name(self):
        return self._name

    @property
    def is_hidden(self):
        return True if self._status is CameraStatus.CAMERA_HIDDEN else False
    
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

    @abstractmethod
    def can_move(self) -> bool:
        """ Check if the camera can be moved """

    def supported_features(self, key: str) -> list[ButtonKey]:
        """ List of supported features """

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
