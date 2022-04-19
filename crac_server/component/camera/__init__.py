

import logging
from crac_server.component.camera.camera import Camera
from crac_server.config import Config
import importlib


logger = logging.getLogger(__name__)


def camera(section: dict) -> Camera:
    driver = section.pop("driver")
    return importlib.import_module(f"crac_server.component.camera.{driver}.camera").Camera(**section)

CAMERA = {
    "camera1": camera(Config.get_section("camera1")),
    "camera2": camera(Config.get_section("camera2")),
}

logger.debug(f"cameras are: {CAMERA}")

def get_camera(name: str) -> Camera:
    logger.debug(f"camera for name: {name}")
    for key, camera in CAMERA.items():
        logger.debug(f"camera is: {camera.name}")
        if camera.name == name:
            return (key, camera)
