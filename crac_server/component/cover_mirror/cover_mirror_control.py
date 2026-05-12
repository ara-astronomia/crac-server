import logging
import json
import re
import socket
import time
import errno

from crac_protobuf.cover_mirror_pb2 import CoverMirrorStatus
from crac_server import config

logger = logging.getLogger(__name__)


class CoverMirrorControl():

    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        self._name = config.Config.getValue("device", "cover_mirror")
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((hostname, port))

    async def open(self):
        logger.debug("Opening mirror cover")
        self.__call({
            "newSwitchVector": {
                "device": self._name,
                "name": "AUX_COVER",
                "items": [
                    {"name": "OPEN", "value": True},
                    {"name": "CLOSE", "value": False}
                ]
            }
        })
        return True

    async def close(self):
        logger.debug("Closing mirror cover")
        self.__call({
            "newSwitchVector": {
                "device": self._name,
                "name": "AUX_COVER",
                "items": [
                    {"name": "OPEN", "value": False},
                    {"name": "CLOSE", "value": True}
                ]
            }
        })
        return True

    def get_status(self):
        root = self.__call({
            "getProperties": {
                "version": 512,
                "device": self._name
            }
        })
        logger.debug(f"Raw root from INDIGO: {root}")
        status = self.__retrieve_status_cover(root)
        logger.debug(f"Cover mirror status is {status}")
        if status == "OPEN":
            return CoverMirrorStatus.COVER_MIRROR_OPENED
        elif status == "CLOSE":
            return CoverMirrorStatus.COVER_MIRROR_CLOSED
        return CoverMirrorStatus.COVER_MIRROR_ERROR

    def __retrieve_status_cover(self, root):
        for item in root:
            if "defSwitchVector" not in item:
                continue
            vector = item["defSwitchVector"]
            if vector.get("name") != "AUX_COVER":
                continue
            for switch in vector.get("items", []):
                if switch.get("value") is True:
                    return switch.get("name", "UNKNOWN")
        return "UNKNOWN"

    def __call(self, script):
        request_json = json.dumps(script)
        self.s.settimeout(1)
        responses = []

        def send_and_receive(request):
            response = b""
            try:
                self.s.sendall(request)
                time.sleep(5)
                while True:
                    try:
                        part = self.s.recv(2500000)
                        if not part:
                            break
                        response += part
                    except socket.timeout:
                        logger.debug("Socket timeout, stopping reception.")
                        break
                return response
            except Exception as e:
                if isinstance(e, socket.error) and e.errno == errno.EPIPE:
                    logger.error(f"Socket error: {e}")

        response_with_newline = send_and_receive(request_json.encode('utf-8') + b'\n')
        if response_with_newline:
            responses.append(response_with_newline.decode('utf-8'))

        response_without_newline = send_and_receive(request_json.encode('utf-8'))
        if response_without_newline:
            responses.append(response_without_newline.decode('utf-8'))

        combined_response = "\n".join(responses)
        json_strings = re.findall(r'\{.*?\}(?=\{|\Z)', combined_response)

        response_objects = []
        for json_str in json_strings:
            try:
                json_obj = json.loads(json_str)
                response_objects.append(json_obj)
            except json.JSONDecodeError as e:
                logger.error(f"Errore nella decodifica del JSON: {e}")

        return response_objects