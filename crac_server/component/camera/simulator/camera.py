from crac_server.component.camera.camera import Camera as CameraBase
from crac_protobuf.camera_pb2 import (
    CameraStatus
)


class Camera(CameraBase):
    def __init__(self, source: str, name: str) -> None:
        super().__init__(source, name)
        self._status = CameraStatus.CAMERA_HIDDEN
    
    def read(self):
        if self.status is CameraStatus.CAMERA_SHOWN:
            return self._streaming.read()
        else:
            return (True, self._streaming._black_frame)

