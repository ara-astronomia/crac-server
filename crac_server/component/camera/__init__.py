

from crac_server.component.camera.simulator.camera import Camera
from crac_server.config import Config


CAMERA = {
    "camera1": Camera(source=Config.getValue("source", "camera1"), name=Config.getValue("name", "camera1")),
    "camera2": Camera(source=Config.getValue("source", "camera2"), name=Config.getValue("name", "camera2")),
}
