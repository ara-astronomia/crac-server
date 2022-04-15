from asyncio.log import logger
from distutils.util import strtobool
from time import sleep
from crac_protobuf.camera_pb2 import (
    CameraStatus
)
from crac_protobuf.button_pb2 import ButtonKey
from crac_server.component.camera.camera import Camera as CameraBase
from libpyfoscam import FoscamCamera


class Camera(CameraBase):
    def __init__(self, name: str, source: str, user: str, host: str, port = "88", password: str = "", streaming: bool = True, settings: bool = True) -> None:
        self._foscam = FoscamCamera(host, port, user, password) if strtobool(settings) else None
        super().__init__(source=self.streamUrl(user, password, host, port, source), name=name, streaming=strtobool(streaming), settings=strtobool(settings))
    
    def refresh_status(self):
        if self.is_hidden:
            self._status = CameraStatus.CAMERA_HIDDEN
        else:
            self._status = CameraStatus.CAMERA_SHOWN
    
    def __callback(self, code, params):
        sleep(0.5)
        self.stop()

    def move_top_left(self):
        self._foscam.ptz_move_top_left(self.__callback)

    def move_up(self):
        self._foscam.ptz_move_up(self.__callback)
    
    def move_top_right(self):
        self._foscam.ptz_move_top_right(self.__callback)

    def move_right(self):
        self._foscam.ptz_move_right(self.__callback)

    def move_bottom_right(self):
        self._foscam.ptz_move_bottom_right(self.__callback)
    
    def move_down(self):
        self._foscam.ptz_move_down(self.__callback)

    def move_bottom_left(self):
        self._foscam.ptz_move_bottom_left(self.__callback)

    def move_left(self):
        self._foscam.ptz_move_left(self.__callback)

    def stop(self):
        self._foscam.ptz_stop_run()
    
    @property
    def ir(self):
        return self._ir
    
    @ir.setter
    def ir(self, mode: int):
        if not self._settings:
            self._ir = 0
            return

        if mode == 2:
            config = 0
        elif mode in (0, 1):
            config = 1
        else:
            raise Exception("Invalid inf_type, can be off, on or auto")

        self._foscam.set_infra_led_config(mode=config)

        if mode == 0:
            self._foscam.close_infra_led()
        elif mode == 1:
            self._foscam.open_infra_led()
        
        self._ir = mode

    def supported_features(self, key: str) -> list[ButtonKey]:
        supported = super().supported_features(key)
        if self._settings:
            supported.append(ButtonKey.KEY_CAMERA_STOP_MOVE)
        return supported
