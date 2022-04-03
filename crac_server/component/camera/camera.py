from abc import ABC, abstractmethod
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_server.component.camera.streaming import Streaming


class Camera(ABC):

    def __init__(self, source: str, name: str) -> None:
        self._name = name
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
