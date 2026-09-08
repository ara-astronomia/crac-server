import logging

from crac_protobuf.cover_mirror_pb2 import CoverMirrorStatus
from crac_server import config
from crac_server.component.indigo_client import get_indigo_client

logger = logging.getLogger(__name__)

STATUS_BY_INDIGO_STATE = {
    "Ok": {
        "OPEN": CoverMirrorStatus.COVER_MIRROR_OPENED,
        "CLOSE": CoverMirrorStatus.COVER_MIRROR_CLOSED,
    },
    "Busy": {
        "OPEN": CoverMirrorStatus.COVER_MIRROR_OPENING,
        "CLOSE": CoverMirrorStatus.COVER_MIRROR_CLOSING,
    },
}


class CoverMirrorControl():

    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        self._name = config.Config.getValue("device", "cover_mirror")
        self._client = get_indigo_client(hostname, port)
        self._client.connect_device(self._name)

    async def open(self):
        logger.info(f"Opening mirror cover: {self._name}")
        return self._client.send({
            "newSwitchVector": {
                "device": self._name,
                "name": "AUX_COVER",
                "items": [
                    {"name": "OPEN", "value": True},
                    {"name": "CLOSE", "value": False}
                ]
            }
        })

    async def close(self):
        logger.info(f"Closing mirror cover: {self._name}")
        return self._client.send({
            "newSwitchVector": {
                "device": self._name,
                "name": "AUX_COVER",
                "items": [
                    {"name": "OPEN", "value": False},
                    {"name": "CLOSE", "value": True}
                ]
            }
        })

    def get_status(self):
        """The switch value tells what was commanded, the INDIGO state tells
        what happened: the driver keeps AUX_COVER Busy while the petals move
        and turns it to Alert when the ESP32 never confirms the movement.
        Any state other than Ok or Busy - a missing one included - means the
        commanded position cannot be trusted, hence an error."""
        self._client.connect_device(self._name)
        prop = self._client.get_property(self._name, "AUX_COVER")
        if not prop:
            logger.error("[CoverMirror] AUX_COVER property not available from INDIGO")
            return CoverMirrorStatus.COVER_MIRROR_ERROR

        state = prop.get("state")
        status_by_switch = STATUS_BY_INDIGO_STATE.get(state)
        if not status_by_switch:
            logger.error(f"[CoverMirror] AUX_COVER in unusable INDIGO state: {state}")
            return CoverMirrorStatus.COVER_MIRROR_ERROR

        for switch in prop.get("items", []):
            if switch.get("value") is True and switch.get("name") in status_by_switch:
                return status_by_switch[switch["name"]]

        return CoverMirrorStatus.COVER_MIRROR_ERROR
