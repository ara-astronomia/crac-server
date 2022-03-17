from crac_protobuf.camera_pb2 import (
    CameraRequest, 
    CameraResponse,
    Move,
    CameraAction,
    CameraStatus
)
import cv2
import numpy as np


class Camera:
    def __init__(self, source="./component/camera/simulator/video/simulated.mp4", width=1280, height=720) -> None:
        self._status = CameraStatus.CAMERA_DISCONNECTED
        self._source = source
        self._camera = None
        self._width = width
        self._height = height
        self._black_frame = np.zeros((height, width, 3), dtype = "uint8")
    
    @property
    def status(self):
        return self._status
    
    def read(self):
        if self._camera and self.status is CameraStatus.CAMERA_SHOWN:
            return self._camera.read()
        else:
            return (True, self._black_frame)
    
    def close(self):
        self._status = CameraStatus.CAMERA_DISCONNECTED
        return self._camera.release()

    def open(self):
        self._camera = cv2.VideoCapture(self._source)
        self._width = int(self._camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._black_frame = np.zeros((self._height, self._width, 3), dtype = "uint8")
        self._status = CameraStatus.CAMERA_HIDDEN

    def show(self):
        self._status = CameraStatus.CAMERA_SHOWN

    def hide(self):
        self._status = CameraStatus.CAMERA_HIDDEN

CAMERA = Camera(0)
