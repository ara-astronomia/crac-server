from abc import ABC, abstractmethod
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_server.component.camera.streaming import Streaming
import numpy as np


class Camera(ABC):

    def __init__(self, source: str, name: str, width: int, height: int) -> None:
        self._status = CameraStatus.CAMERA_DISCONNECTED
        self._streaming = Streaming(source, name, width, height)
        self._name = name
        self._width = width
        self._height = height
        self._black_frame = np.zeros((height, width, 3), dtype = "uint8")


    @property
    def status(self):
        return self._status
    
    @property
    def name(self):
        return self._name

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
    def read(self):
        """ Read the streaming frame by frame """