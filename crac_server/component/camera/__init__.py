

from crac_server.component.camera.camera import Camera
from crac_server.config import Config
import importlib


def camera(section) -> Camera:
    driver = section.pop("driver")
    return importlib.import_module(f"crac_server.component.camera.{driver}.camera").Camera(**section)

CAMERA = {
    "camera1": camera(Config.get_section("camera1")),
    "camera2": camera(Config.get_section("camera2")),
}
