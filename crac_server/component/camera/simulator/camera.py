from crac_server.component.camera.camera import Camera as CameraBase
from crac_protobuf.camera_pb2 import (
    CameraStatus
)


class Camera(CameraBase):
    def __init__(self, source: str, name: str) -> None:
        super().__init__(source, name)
        self._move = False
    
    @property
    def can_move(self):
        return self._move

    def move_top_left(self, seconds: float):
        raise NotImplementedError()

    def move_up(self, seconds: float):
        raise NotImplementedError()

    def move_top_right(self, seconds: float):
        raise NotImplementedError()

    def move_right(self, seconds: float):
        raise NotImplementedError()

    def move_bottom_right(self, seconds: float):
        raise NotImplementedError()
    
    def move_down(self, seconds: float):
        raise NotImplementedError()

    def move_bottom_left(self, seconds: float):
        raise NotImplementedError()

    def move_left(self, seconds: float):
        raise NotImplementedError()

    def stop(self, seconds: float):
        raise NotImplementedError()
