from crac_server.component.camera.camera import Camera as CameraBase
from crac_protobuf.camera_pb2 import (
    CameraStatus
)


class Camera(CameraBase):
    def __init__(self, source: str, name: str, width=1280, height=720) -> None:
        super().__init__(source, name, width, height)
    
    def read(self):
        if self.status is CameraStatus.CAMERA_SHOWN:
            return self._streaming.read()
        else:
            return (True, self._black_frame)

