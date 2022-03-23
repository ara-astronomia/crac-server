import cv2
from cv2 import VideoCapture
import numpy as np


class Streaming:

    def __init__(self, source: str, name: str, width: int, height: int) -> None:
        self._source = 0 if source == "0" else source
        self._name = name
        self._video_capture: VideoCapture = None
        self._width = width
        self._height = height
        self._black_frame = np.zeros((height, width, 3), dtype = "uint8")
    
    def close(self):
        self._video_capture = None

    def open(self):
        try:
            if not self._video_capture:
                self._video_capture = cv2.VideoCapture(self._source)
                self._width = int(self._video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                self._height = int(self._video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self._black_frame = np.zeros((self._height, self._width, 3), dtype = "uint8")
            return True
        except:
            return False
    
    def read(self):
        if self._video_capture:
            return self._video_capture.read()
        else:
            raise StreamingError(f"Streaming for camera {self._name} is not open")

class StreamingError(Exception):
    pass