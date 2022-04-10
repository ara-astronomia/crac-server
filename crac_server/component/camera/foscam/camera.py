from time import sleep
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_protobuf.button_pb2 import ButtonKey
from crac_server.component.camera.camera import Camera as CameraBase
import urllib
from libpyfoscam import FoscamCamera


class Camera(CameraBase):
    def __init__(self, name: str, user: str, host: str, port = "88", password: str = "", source: str = None) -> None:
        super().__init__(self.streamUrl(user, password, host, port, source), name)
        self._foscam = FoscamCamera(host, port, user, password)
        self._move = True
    
    def refresh_status(self):
        if self.is_hidden:
            self._status = CameraStatus.CAMERA_HIDDEN
        else:
            self._status = CameraStatus.CAMERA_SHOWN
        
    def streamUrl(self, user: str, password: str, host: str, port: str, stream: str):
        return f"rtsp://{urllib.parse.quote_plus(user)}:{urllib.parse.quote_plus(password)}@{host}:{port}/{stream}"
    
    def __callback(self, code, params):
        sleep(0.5)
        self.stop()
    
    @property
    def can_move(self):
        return self._move

    def move_top_left(self):
        self._foscam.ptz_move_top_left(self.__callback)

    def move_up(self):
        self._foscam.ptz_move_up(self.__callback)
    
    def move_top_right(self):
        self._foscam.ptz_move_top_right(self.__callback)

    def move_right(self):
        self._foscam.ptz_move_right(self.__callback)

    def move_bottom_right(self):
        self._foscam.ptz_move_bottom_right(self.__callback)
    
    def move_down(self):
        self._foscam.ptz_move_down(self.__callback)

    def move_bottom_left(self):
        self._foscam.ptz_move_bottom_left(self.__callback)

    def move_left(self):
        self._foscam.ptz_move_left(self.__callback)

    def stop(self):
        self._foscam.ptz_stop_run()

    def supported_features(self, key: str) -> list[ButtonKey]:
        supported = super().supported_features(key)
        supported.append(ButtonKey.KEY_CAMERA_STOP_MOVE)
        return supported
