import cv2
from cv2 import VideoCapture
import numpy as np


class Streaming:

    def __init__(self, source: str, name: str) -> None:
        self._source = 0 if source == "0" else source
        self._name = name
        self._video_capture: VideoCapture = None
        self._black_frame = None
    
    def close(self):
        self._video_capture = None

    def open(self):
        try:
            if not self._video_capture:
                self._video_capture = cv2.VideoCapture(self._source)
                width = int(self._video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self._video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self._black_frame = self.__set_black_frame(width=width, height=height)
            return True
        except:
            return False
    
    def read(self):
        if self._video_capture:
            ret, frame = self._video_capture.read()
            if ret:
                return (ret, frame)
            elif self._source.endswith(".mp4"):
                self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._video_capture.read()
                if ret:
                    return (ret, frame)
                else:
                    return (True, self._black_frame)
            else:
                return (True, self._black_frame)
        else:
            raise StreamingError(f"Streaming for camera {self._name} is not open")
    
    def __set_black_frame(self, width: int, height: int):
        return np.zeros((height, width, 3), dtype = "uint8")

class StreamingError(Exception):
    pass
