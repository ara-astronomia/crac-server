from distutils.util import strtobool
from crac_server.component.camera.camera import Camera as CameraBase


class Camera(CameraBase):
    def __init__(self, name: str, source: str, user=None, host=None, port=None, password=None, streaming: bool = True, settings: bool = False) -> None:
        super().__init__(source=source, name=name, streaming=strtobool(streaming), settings=strtobool(settings))

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
        return self._base_supported_features(key)
