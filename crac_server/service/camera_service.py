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
    CameraStatus,
    Move,
    CameraDevice,
)
from crac_protobuf.camera_pb2_grpc import CameraServicer
from crac_protobuf.roof_pb2 import RoofStatus
from crac_protobuf.telescope_pb2 import TelescopeSpeed
from crac_server.component.button_control import SWITCHES
from crac_server.component.camera import CAMERA, get_camera
import cv2
from crac_server.component.camera.camera import Camera
from crac_server.component.roof import ROOF

from crac_server.component.telescope import TELESCOPE
from crac_server.config import Config


logger = logging.getLogger(__name__)


class CameraService(CameraServicer):
    def __init__(self) -> None:
        super().__init__()

    def Video(self, request: CameraRequest, context) -> CameraResponse:
        logger.debug(f"Process id is {os.getpid()}")
        key, camera = self.__get_camera(request.name)
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
            yield CameraResponse(video=video, ir=False, status=camera.status, name=key)

    def SetAction(self, request: CameraRequest, context) -> CameraResponse:
        logger.info("Request " + str(request))
        key, camera = self.__get_camera(request.name)

        camera_display = self.__display(key)
        camera_connection = self.__connection(key)
        camera_ir = ButtonKey.KEY_CAMERA1_IR_TOGGLE if key == "camera1" else ButtonKey.KEY_CAMERA2_IR_TOGGLE

        supported_features = camera.supported_features(key)

        logger.debug(f"Key={key}, Camera={camera}, ir={camera.ir}")
        if request.action is CameraAction.CAMERA_DISCONNECT and camera_connection in supported_features:
            camera.close()
        elif request.action is CameraAction.CAMERA_CONNECT and camera_connection in supported_features:
            camera.open()
        elif request.action is CameraAction.CAMERA_MOVE and self.__move_to_key(request.move) in supported_features:
            logger.debug("Camera is moving")
            self.__move_camera(camera, request.move)
        elif (
            request.action is CameraAction.CAMERA_HIDE or
            (request.action is CameraAction.CAMERA_CHECK and request.autodisplay and not self.__show_camera()) and
            camera_display in supported_features
        ):
            camera.hide()
        elif (
            request.action is CameraAction.CAMERA_SHOW or
            (request.action is CameraAction.CAMERA_CHECK and request.autodisplay and self.__show_camera()) and
            camera_display in supported_features
        ):
            camera.show()
        elif request.action == CameraAction.CAMERA_IR_ENABLE and camera_ir in supported_features:
            logger.debug("Camera is enabling ir")
            camera.ir = 1
        elif request.action == CameraAction.CAMERA_IR_DISABLE and camera_ir in supported_features:
            logger.debug("Camera is disabling ir")
            camera.ir = 0
        elif request.action == CameraAction.CAMERA_IR_AUTO and camera_ir in supported_features:
            logger.debug("Camera is auto ir")
            camera.ir = 2
        logger.debug(f"IR mode is {camera.ir}")

        logger.debug(f"camera connection: {camera_connection}")
        logger.debug(f"camera display: {camera_display}")
        logger.debug(f"camera ir: {camera_ir}")

        if camera.status is CameraStatus.CAMERA_DISCONNECTED:
            connect_label = ButtonLabel.LABEL_CAMERA_DISCONNECTED
            connect_color = ButtonColor(
                text_color="white",
                background_color="red"
            )
            connect_metadata = CameraAction.CAMERA_CONNECT
        else:
            connect_label = ButtonLabel.LABEL_CAMERA_CONNECTED
            connect_color = ButtonColor(
                text_color="white",
                background_color="green"
            )
            connect_metadata = CameraAction.CAMERA_DISCONNECT

        if camera.status in (CameraStatus.CAMERA_DISCONNECTED, CameraStatus.CAMERA_HIDDEN):
            display_label = ButtonLabel.LABEL_CAMERA_HIDDEN
            display_color = ButtonColor(
                text_color="white",
                background_color="red"
            )
            display_metadata = CameraAction.CAMERA_SHOW
            if camera.status is CameraStatus.CAMERA_DISCONNECTED or camera_display not in supported_features:
                display_is_disabled = True
            else:
                display_is_disabled = False
        else:
            display_label = ButtonLabel.LABEL_CAMERA_SHOWN
            display_color = ButtonColor(
                text_color="white",
                background_color="green"
            )
            display_metadata = CameraAction.CAMERA_HIDE
            display_is_disabled = False

        connection_visible = camera_connection in supported_features
        display_visible = camera_display in supported_features
        ir_visible = camera_ir in supported_features
        ir_metadata = CameraAction.CAMERA_IR_DISABLE if camera.ir == 1 else CameraAction.CAMERA_IR_ENABLE
        ir_background = "green" if camera.ir == 1 else "red"
        ir_label = ButtonLabel.LABEL_CAMERA_IR_ENABLED if camera.ir != 0 else ButtonLabel.LABEL_CAMERA_IR_DISABLED

        connection_button = ButtonGui(
            key=camera_connection,
            label=connect_label,
            is_disabled=True,
            metadata=connect_metadata,
            button_color=connect_color,
            is_visible=connection_visible
        )
        display_button = ButtonGui(
            key=camera_display,
            label=display_label,
            is_disabled=display_is_disabled,
            metadata=display_metadata,
            button_color=display_color,
            is_visible=display_visible
        )
        ir_button = ButtonGui(
            key=camera_ir,
            label=ir_label,
            is_disabled=False,
            metadata=ir_metadata,
            button_color=ButtonColor(
                text_color="white",
                background_color=ir_background
            ),
            is_visible=ir_visible
        )

        buttons = (connection_button, display_button, ir_button)
        logger.debug(f"Supported features are {supported_features}")
        logger.debug(
            f"buttons are {(connection_button, display_button, ir_button)}")
        return CameraResponse(ir=camera.ir != 0, status=camera.status, buttons_gui=buttons, name=key)

    def ListCameras(self, request: CameraRequest, context) -> CamerasResponse:
        key1 = "camera1"
        key2 = "camera2"
        logger.debug(f"camera1 is {CAMERA[key1].supported_features(key1)}")
        logger.debug(f"camera2 is {CAMERA[key2].supported_features(key2)}")
        if CAMERA[key1]:
            camera_device1 = CameraDevice(name=Config.getValue(
                "name", key1), features=CAMERA[key1].supported_features(key1))
        else:
            camera_device1 = None

        if CAMERA[key2]:
            camera_device2 = CameraDevice(name=Config.getValue(
                "name", key2), features=CAMERA[key2].supported_features(key2))
        else:
            camera_device2 = None

        return CamerasResponse(camera1=camera_device1, camera2=camera_device2)

    def __show_camera(self) -> bool:
        return (
            TELESCOPE.speed is TelescopeSpeed.SPEED_SLEWING or
            SWITCHES["DOME_LIGHT"].get_status() is ButtonStatus.ON or
            ROOF.get_status() in [RoofStatus.ROOF_OPENING,
                                  RoofStatus.ROOF_CLOSING]
        )

    def __move_camera(self, camera: Camera, move: Move):
        logger.debug(f"Movement is {move}")
        if move is Move.MOVE_UP:
            camera.move_up()
        elif move is Move.MOVE_TOP_RIGHT:
            camera.move_top_right()
        elif move is Move.MOVE_RIGHT:
            camera.move_right()
        elif move is Move.MOVE_BOTTOM_RIGHT:
            camera.move_bottom_right()
        elif move is Move.MOVE_DOWN:
            camera.move_down()
        elif move is Move.MOVE_BOTTOM_LEFT:
            camera.move_bottom_left()
        elif move is Move.MOVE_LEFT:
            camera.move_left()
        elif move is Move.MOVE_TOP_LEFT:
            camera.move_top_left()
        elif move is Move.MOVE_STOP:
            camera.stop()

    def __get_camera(self, name_or_key: str) -> tuple[str, Camera]:
        camera = CAMERA.get(name_or_key)
        logger.debug(f"Camera col get: {camera}")
        return (name_or_key, camera) if camera else get_camera(name_or_key)

    def __display(self, key: str) -> ButtonKey:
        if key == "camera1":
            return ButtonKey.KEY_CAMERA1_DISPLAY
        if key == "camera2":
            return ButtonKey.KEY_CAMERA2_DISPLAY

    def __connection(self, key: str) -> ButtonKey:
        if key == "camera1":
            return ButtonKey.KEY_CAMERA1_CONNECTION
        if key == "camera2":
            return ButtonKey.KEY_CAMERA2_CONNECTION

    def __move_to_key(self, move: Move) -> ButtonKey:
        return {
            Move.MOVE_STOP: ButtonKey.KEY_CAMERA_STOP_MOVE,
            Move.MOVE_UP: ButtonKey.KEY_CAMERA_MOVE_UP,
            Move.MOVE_TOP_RIGHT: ButtonKey.KEY_CAMERA_MOVE_TOP_RIGHT,
            Move.MOVE_RIGHT: ButtonKey.KEY_CAMERA_MOVE_RIGHT,
            Move.MOVE_BOTTOM_RIGHT: ButtonKey.KEY_CAMERA_MOVE_BOTTOM_RIGHT,
            Move.MOVE_DOWN: ButtonKey.KEY_CAMERA_MOVE_DOWN,
            Move.MOVE_BOTTOM_LEFT: ButtonKey.KEY_CAMERA_MOVE_BOTTOM_LEFT,
            Move.MOVE_LEFT: ButtonKey.KEY_CAMERA_MOVE_LEFT,
            Move.MOVE_TOP_LEFT: ButtonKey.KEY_CAMERA_MOVE_TOP_LEFT,
        }[move]
