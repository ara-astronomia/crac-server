from crac_protobuf.camera_pb2 import (
    CameraRequest, 
    CameraResponse,
    Move,
)
from crac_protobuf.camera_pb2_grpc import CameraServicer
import cv2


class CameraService(CameraServicer):
    def Video(self, request: CameraRequest, context) -> CameraResponse:
        input_video_path = "./component/camera/simulator/video/simulated.mp4"
        camera = cv2.VideoCapture(0)
        while True:
            success, frame = camera.read()  # read the camera frame
            if not success:
                break
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    break
                frame = buffer.tobytes()
                video = (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')  # concat frame one by one and show result
            yield CameraResponse(move=Move.MOVE_STOP, video=video, ir=False)
