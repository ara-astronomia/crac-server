import logging
import os
from crac_protobuf.button_pb2 import (
    ButtonGui,
    ButtonLabel,
    ButtonKey,
    ButtonColor,
    ButtonStatus
)
from crac_protobuf.camera_pb2 import (
    CameraRequest, 
    CameraResponse,
    CamerasResponse,
    CameraAction,
    CameraStatus
)
from crac_protobuf.camera_pb2_grpc import CameraServicer
from crac_protobuf.roof_pb2 import RoofStatus
from crac_protobuf.telescope_pb2 import TelescopeSpeed
from crac_server.component.button_control import SWITCHES
from crac_server.component.camera import CAMERA
import cv2
from crac_server.component.roof import ROOF

from crac_server.component.telescope import TELESCOPE
from crac_server.config import Config


logger = logging.getLogger(__name__)


class CameraService(CameraServicer):
    def __init__(self) -> None:
        super().__init__()

    def Video(self, request: CameraRequest, context) -> CameraResponse:
        logger.debug(f"Process id is {os.getpid()}")
        camera = CAMERA[request.name]
        while True:
            success, frame = camera.read()  # read the camera frame
            if not success:
                break
            elif frame.size == 0:
                continue
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    break
                frame_bytes = buffer.tobytes()
                video = (
                    b'--frame\r\n' +
                    b'Content-Type: image/jpeg\r\n\r\n' + 
                    frame_bytes + 
                    b'\r\n'
                )
            yield CameraResponse(video=video, ir=False, status=camera.status, name=request.name)

    def SetAction(self, request: CameraRequest, context) -> CameraResponse:
        camera = CAMERA[request.name]
        if request.action is CameraAction.CAMERA_DISCONNECT:
            camera.close()
        elif request.action is CameraAction.CAMERA_CONNECT:
            camera.open()
        elif request.action is CameraAction.CAMERA_HIDE or (request.autodisplay and not self.__show_camera()):
            camera.hide()
        elif request.action is CameraAction.CAMERA_SHOW or (request.autodisplay and self.__show_camera()):
            camera.show()

        if camera.status is CameraStatus.CAMERA_DISCONNECTED:
            connect_label = ButtonLabel.LABEL_CAMERA_DISCONNECTED
            connect_color = ButtonColor(
                text_color = "white",
                background_color = "red"
            )
            connect_metadata = CameraAction.CAMERA_CONNECT
        else:
            connect_label = ButtonLabel.LABEL_CAMERA_CONNECTED
            connect_color = ButtonColor(
                text_color = "white",
                background_color = "green"
            )
            connect_metadata = CameraAction.CAMERA_DISCONNECT

        if camera.status in (CameraStatus.CAMERA_DISCONNECTED, CameraStatus.CAMERA_HIDDEN):
            display_label = ButtonLabel.LABEL_CAMERA_HIDDEN
            display_color = ButtonColor(
                text_color = "white",
                background_color = "red"
            )
            display_metadata = CameraAction.CAMERA_SHOW
            if camera.status is CameraStatus.CAMERA_DISCONNECTED:
                display_is_disabled = True
            else:
                display_is_disabled = False
        else:
            display_label = ButtonLabel.LABEL_CAMERA_SHOWN
            display_color = ButtonColor(
                text_color = "white",
                background_color = "green"
            )
            display_metadata = CameraAction.CAMERA_HIDE
            display_is_disabled = False

        connection_button = ButtonGui(
            key=ButtonKey.KEY_CAMERA1_CONNECTION if request.name == "camera1" else ButtonKey.KEY_CAMERA2_CONNECTION,
            label=connect_label,
            is_disabled=True,
            metadata=connect_metadata,
            button_color=connect_color,
        )
        display_button = ButtonGui(
            key=ButtonKey.KEY_CAMERA1_DISPLAY if request.name == "camera1" else ButtonKey.KEY_CAMERA2_DISPLAY,
            label=display_label,
            is_disabled=display_is_disabled,
            metadata=display_metadata,
            button_color=display_color,
        )
        buttons = (connection_button, display_button)
        
        return CameraResponse(ir=False, status=camera.status, buttons_gui=buttons, name=request.name)
    
    def ListCameras(self, request: CameraRequest, context) -> CamerasResponse:

        return CamerasResponse(camera1=Config.getValue("name", "camera1"), camera2=Config.getValue("name", "camera2"))

    def __show_camera(self) -> bool:
        return (
            TELESCOPE.speed is TelescopeSpeed.SPEED_SLEWING or
            SWITCHES["DOME_LIGHT"].get_status() is ButtonStatus.ON or 
            ROOF.get_status() in [RoofStatus.ROOF_OPENING, RoofStatus.ROOF_CLOSING]
        )
