import cv2
import urllib
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_server.component.camera.camera import Camera as CameraBase
from pytapo import Tapo

from crac_server.config import Config


class Camera(CameraBase):
    def __init__(self, source: str, name: str, user: str, password: str, host: str, port = 554, width=1280, height=720) -> None:
        self._user = user
        self._password = password
        self._host = host
        self._port = port
        self._source = source
        super().__init__(self.streamUrl(self._source), name, width, height)
        self._tapo = Tapo(host, user, password)
    
    @property
    def tapo(self):
        return self._tapo

    def read(self):
        return self._streaming.read()

    def show(self):
        if self._status is not CameraStatus.CAMERA_DISCONNECTED:
            self._tapo.setPrivacyMode(False)
            self._status = CameraStatus.CAMERA_SHOWN

    def hide(self):
        if self._status is not CameraStatus.CAMERA_DISCONNECTED:
            self._tapo.setPrivacyMode(True)
            self._status = CameraStatus.CAMERA_HIDDEN
    
    def streamUrl(self, streamType="stream1"):
        return f"rtsp://{urllib.parse.quote_plus(self._user)}:{urllib.parse.quote_plus(self._password)}@{self._host}:{self._port}/{streamType}"

if __name__ == "__main__":

    # user = "alkcxy"
    # password = "Q51md9.547"
    # host = "192.168.0.80"
    # tapo = Tapo(host, user, password)

    streamType = "stream2"
    # streamURL = f"rtsp://{urllib.parse.quote_plus(user)}:{urllib.parse.quote_plus(password)}@{host}:554/{streamType}"

    camera = Camera(streamType, Config.getValue("name", "camera2"), Config.getValue("user", "camera2"), Config.getValue("password", "camera2"), Config.getValue("host", "camera2"))
    camera.open()
    print(camera.read())
    camera.show()
    print(camera.read())
    camera.hide()