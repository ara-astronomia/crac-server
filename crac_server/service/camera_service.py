from crac_protobuf.button_pb2 import (
    ButtonGui,
    ButtonLabel,
    ButtonKey,
    ButtonColor,
)
from crac_protobuf.camera_pb2 import (
    CameraRequest, 
    CameraResponse,
    CameraAction,
    CameraStatus
)
from crac_protobuf.camera_pb2_grpc import CameraServicer
from crac_server.component.camera import CAMERA
import cv2


class CameraService(CameraServicer):
    def __init__(self) -> None:
        super().__init__()

    def Video(self, request: CameraRequest, context) -> CameraResponse:
        camera = CAMERA[request.name]
        while True:
            success, frame = camera.read()  # read the camera frame
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
            yield CameraResponse(video=video, ir=False, status=camera.status)

    def SetAction(self, request: CameraRequest, context) -> CameraResponse:
        camera = CAMERA[request.name]
        if request.action is CameraAction.CAMERA_DISCONNECT:
            camera.close()
        elif request.action is CameraAction.CAMERA_CONNECT:
            camera.open()
        elif request.action is CameraAction.CAMERA_HIDE:
            camera.hide()
        elif request.action is CameraAction.CAMERA_SHOW:
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
        
        return CameraResponse(ir=False, status=camera.status, buttons_gui=buttons)
