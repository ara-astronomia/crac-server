from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_server.component.camera.camera import Camera as CameraBase
import urllib


class Camera(CameraBase):
    def __init__(self, source: str, name: str, user: str, host: str, port = "88", password: str = "") -> None:
        super().__init__(self.streamUrl(user, password, host, port, source), name)
    
    @property
    def is_hidden(self):
        return True if self._status is CameraStatus.CAMERA_HIDDEN else False
    
    def refresh_status(self):
        if self.is_hidden:
            self._status = CameraStatus.CAMERA_HIDDEN
        else:
            self._status = CameraStatus.CAMERA_SHOWN

    def read(self):
        return self._streaming.read()

    def show(self):
        self._status = CameraStatus.CAMERA_SHOWN

    def hide(self):
        self._status = CameraStatus.CAMERA_HIDDEN
        
    def streamUrl(self, user: str, password: str, host: str, port: str, stream: str):
        return f"rtsp://{urllib.parse.quote_plus(user)}:{urllib.parse.quote_plus(password)}@{host}:{port}/{stream}"
