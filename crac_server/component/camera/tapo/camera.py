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
    
    @property
    def tapo(self):
        return self._tapo
    
    @property
    def is_hidden(self):
        privacy_mode = self._tapo.getPrivacyMode()
        return bool(privacy_mode["enabled"])
    
    def refresh_status(self):
        if self.is_hidden:
            self._status = CameraStatus.CAMERA_HIDDEN
        else:
            self._status = CameraStatus.CAMERA_SHOWN

    def read(self):
        return self._streaming.read()

    def show(self):
        self._tapo.setPrivacyMode(False)
        self._status = CameraStatus.CAMERA_SHOWN

    def hide(self):
        self._tapo.setPrivacyMode(True)
        self._status = CameraStatus.CAMERA_HIDDEN
        
    def streamUrl(self, user: str, password: str, host: str, port: str, stream: str):
        return f"rtsp://{urllib.parse.quote_plus(user)}:{urllib.parse.quote_plus(password)}@{host}:{port}/{stream}"
