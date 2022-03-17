from crac_protobuf.button_pb2 import (
    ButtonGui,
    ButtonLabel,
    ButtonKey,
    ButtonColor,
    ButtonStatus,
)
from crac_protobuf.camera_pb2 import (
    CameraRequest, 
    CameraResponse,
    Move,
    CameraAction,
    CameraStatus
)
from crac_protobuf.camera_pb2_grpc import CameraServicer
from crac_server.component.camera.simulator.camera import CAMERA
import cv2


class CameraService(CameraServicer):
    def __init__(self) -> None:
        super().__init__()

    def Video(self, request: CameraRequest, context) -> CameraResponse:
        while True:
            success, frame = CAMERA.read()  # read the camera frame
            if not success:
                break
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    break
                frame = buffer.tobytes()
                video = (
                    b'--frame\r\n' +
                    b'Content-Type: image/jpeg\r\n\r\n' + 
                    frame + 
                    b'\r\n'
                )
            yield CameraResponse(move=Move.MOVE_STOP, video=video, ir=False)

    def SetAction(self, request: CameraRequest, context) -> CameraResponse:
        if request.action is CameraAction.CAMERA_DISCONNECT:
            CAMERA.close()
        elif request.action is CameraAction.CAMERA_CONNECT:
            CAMERA.open()
        elif request.action is CameraAction.CAMERA_HIDE:
            CAMERA.hide()
        elif request.action is CameraAction.CAMERA_SHOW:
            CAMERA.show()

        if CAMERA.status is CameraStatus.CAMERA_DISCONNECTED:
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

        if CAMERA.status in (CameraStatus.CAMERA_DISCONNECTED, CameraStatus.CAMERA_HIDDEN):
            display_label = ButtonLabel.LABEL_CAMERA_HIDDEN
            display_color = ButtonColor(
                text_color = "white",
                background_color = "red"
            )
            display_metadata = CameraAction.CAMERA_SHOW
            display_is_disabled = False if CameraStatus.CAMERA_HIDDEN else True
        else:
            display_label = ButtonLabel.LABEL_CAMERA_SHOWN
            display_color = ButtonColor(
                text_color = "white",
                background_color = "green"
            )
            display_metadata = CameraAction.CAMERA_HIDE
            display_is_disabled = False

        connection_button = ButtonGui(
            key=ButtonKey.KEY_CAMERA_CONNECTION,
            label=connect_label,
            is_disabled=False,
            metadata=connect_metadata,
            button_color=connect_color,
        )
        display_button = ButtonGui(
            key=ButtonKey.KEY_CAMERA_DISPLAY,
            label=display_label,
            is_disabled=display_is_disabled,
            metadata=display_metadata,
            button_color=display_color,
        )
        buttons = (connection_button, display_button)
        
        return CameraResponse(move=Move.MOVE_STOP, ir=False, status=CAMERA.status, buttons_gui=buttons)
