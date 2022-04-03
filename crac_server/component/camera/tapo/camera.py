from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_server.component.camera.camera import Camera as CameraBase
from pytapo import Tapo
import urllib


class Camera(CameraBase):
    def __init__(self, source: str, name: str, user: str, password: str, host: str, port = "554") -> None:
        self._tapo = Tapo(host, user, password)
        super().__init__(self.streamUrl(user, password, host, port, source), name)
        self.refresh_status()
    
    def open(self):
        self._tapo.setPrivacyMode(False)
        super().open()
    
    def close(self):
        self._tapo.setPrivacyMode(True)
        super().close()
    
    @property
    def tapo(self):
        return self._tapo
    
    def refresh_status(self):
        if self.is_hidden:
            self._status = CameraStatus.CAMERA_HIDDEN
        else:
            self._status = CameraStatus.CAMERA_SHOWN

    def streamUrl(self, user: str, password: str, host: str, port: str, stream: str):
        return f"rtsp://{urllib.parse.quote_plus(user)}:{urllib.parse.quote_plus(password)}@{host}:{port}/{stream}"
