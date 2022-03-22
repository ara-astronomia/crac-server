from typing import Any
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
import cv2
import numpy as np

from crac_server.config import Config


class Camera:
    def __init__(self, source: str, name: str, width=1280, height=720) -> None:
        self._status = CameraStatus.CAMERA_DISCONNECTED
        self._source = 0 if source == "0" else source
        self._name = name
        self._camera = None
        self._width = width
        self._height = height
        self._black_frame = np.zeros((height, width, 3), dtype = "uint8")
    
    @property
    def status(self):
        return self._status
    
    @property
    def name(self):
        return self._name
    
    def read(self):
        if self._camera and self.status is CameraStatus.CAMERA_SHOWN:
            return self._camera.read()
        else:
            return (True, self._black_frame)
    
    def close(self):
        self._status = CameraStatus.CAMERA_DISCONNECTED
        if self._camera:
            is_closed = self._camera.release()
            self._camera = None
            return is_closed

    def open(self):
        self._camera = cv2.VideoCapture(self._source)
        self._width = int(self._camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._black_frame = np.zeros((self._height, self._width, 3), dtype = "uint8")
        self._status = CameraStatus.CAMERA_HIDDEN

    def show(self):
        if self._status is not CameraStatus.CAMERA_DISCONNECTED:
            self._status = CameraStatus.CAMERA_SHOWN

    def hide(self):
        if self._status is not CameraStatus.CAMERA_DISCONNECTED:
            self._status = CameraStatus.CAMERA_HIDDEN
