

from crac_server.component.camera.simulator.camera import Camera
from crac_server.config import Config


CAMERA = {
    "camera1": Camera(Config.getValue("source", "camera1")),
    "camera2": Camera(Config.getValue("source", "camera2")),
}
