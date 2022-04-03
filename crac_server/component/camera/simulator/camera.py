from crac_server.component.camera.camera import Camera as CameraBase
from crac_protobuf.camera_pb2 import (
    CameraStatus
)


class Camera(CameraBase):
    def __init__(self, source: str, name: str) -> None:
        super().__init__(source, name)

