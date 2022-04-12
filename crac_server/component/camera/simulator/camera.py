from crac_server.component.camera.camera import Camera as CameraBase
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_protobuf.button_pb2 import ButtonKey


class Camera(CameraBase):
    def __init__(self, source: str, name: str) -> None:
        super().__init__(source, name)

    def move_top_left(self):
        raise NotImplementedError()

    def move_up(self):
        raise NotImplementedError()

    def move_top_right(self):
        raise NotImplementedError()

    def move_right(self):
        raise NotImplementedError()

    def move_bottom_right(self):
        raise NotImplementedError()
    
    def move_down(self):
        raise NotImplementedError()

    def move_bottom_left(self):
        raise NotImplementedError()

    def move_left(self):
        raise NotImplementedError()

    def stop(self):
        raise NotImplementedError()
    
    def ir(self, mode: int):
        raise NotImplementedError()
    
    def supported_features(self, key: str):
        supported = []
        if key == "camera1":
            supported.append(ButtonKey.KEY_CAMERA1_DISPLAY)
        elif key == "camera2":
            supported.append(ButtonKey.KEY_CAMERA2_DISPLAY)
        return supported
