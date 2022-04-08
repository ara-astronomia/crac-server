from time import sleep
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_server.component.camera.camera import Camera as CameraBase
import urllib
from libpyfoscam import FoscamCamera


class Camera(CameraBase):
    def __init__(self, source: str, name: str, user: str, host: str, port = "88", password: str = "") -> None:
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
    
    @property
    def can_move(self):
        return self._move

    def move_top_left(self, seconds: float):
        self._foscam.ptz_move_top_left()
        sleep(seconds)
        self._foscam.ptz_stop_run()

    def move_up(self, seconds: float):
        self._foscam.ptz_move_up()
        sleep(seconds)
        self._foscam.ptz_stop_run()
    
    def move_top_right(self, seconds: float):
        self._foscam.ptz_move_top_right()
        sleep(seconds)
        self._foscam.ptz_stop_run()

    def move_right(self, seconds: float):
        self._foscam.ptz_move_right()
        sleep(seconds)
        self._foscam.ptz_stop_run()

    def move_bottom_right(self, seconds: float):
        self._foscam.ptz_move_bottom_right()
        sleep(seconds)
        self._foscam.ptz_stop_run()
    
    def move_down(self, seconds: float):
        self._foscam.ptz_move_down()
        sleep(seconds)
        self._foscam.ptz_stop_run()

    def move_bottom_left(self, seconds: float):
        self._foscam.ptz_move_bottom_left()
        sleep(seconds)
        self._foscam.ptz_stop_run()

    def move_left(self, seconds: float):
        self._foscam.ptz_move_left()
        sleep(seconds)
        self._foscam.ptz_stop_run()

    def stop(self):
        self._foscam.ptz_stop_run()
