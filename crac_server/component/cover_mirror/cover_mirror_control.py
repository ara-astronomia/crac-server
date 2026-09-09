import logging

from crac_protobuf.cover_mirror_pb2 import CoverMirrorAction, CoverMirrorStatus
from crac_server import config
from crac_server.component.client.indigo_client import get_indigo_client
from crac_server.status_log import ErrorCause, StatusLogger

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

ACTION_BY_SWITCH = {
    "OPEN": CoverMirrorAction.OPEN_COVER_MIRROR,
    "CLOSE": CoverMirrorAction.CLOSE_COVER_MIRROR,
}


class CoverMirrorControl():

    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        self._name = config.Config.getValue("device", "cover_mirror")
        self._client = get_indigo_client(hostname, port)
        self._client.connect_device(self._name)
        self._status_log = StatusLogger(logger, "CoverMirror", CoverMirrorStatus)

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
            self._status_log.record(
                CoverMirrorStatus.COVER_MIRROR_ERROR, ErrorCause.DEVICE_UNREACHABLE,
                detail="AUX_COVER not available from INDIGO",
            )
            return CoverMirrorStatus.COVER_MIRROR_ERROR

        state = prop.get("state")
        status_by_switch = STATUS_BY_INDIGO_STATE.get(state)
        if not status_by_switch:
            self._status_log.record(
                CoverMirrorStatus.COVER_MIRROR_ERROR,
                ErrorCause.MOVEMENT_NOT_CONFIRMED if state == "Alert" else ErrorCause.STATE_NOT_RECOGNIZED,
                detail=f"INDIGO state: {state}",
            )
            return CoverMirrorStatus.COVER_MIRROR_ERROR

        for switch in prop.get("items", []):
            if switch.get("value") is True and switch.get("name") in status_by_switch:
                status = status_by_switch[switch["name"]]
                self._status_log.record(status)
                return status

        self._status_log.record(
            CoverMirrorStatus.COVER_MIRROR_ERROR, ErrorCause.STATE_NOT_RECOGNIZED,
            detail="no switch reported as active",
        )
        return CoverMirrorStatus.COVER_MIRROR_ERROR

    def get_commanded_action(self):
        """The switch that is still true carries the movement last commanded,
        the only one that survives a failure: after a close that never
        completed the operator still wants to close, not to open.

        Read without waiting: get_status() has just looked the property up, so
        a miss here means it is absent, not late."""
        prop = self._client.get_property(self._name, "AUX_COVER", timeout=0)
        if not prop:
            return CoverMirrorAction.COVER_MIRROR_DEFAULT_ACTION

        for switch in prop.get("items", []):
            if switch.get("value") is True and switch.get("name") in ACTION_BY_SWITCH:
                return ACTION_BY_SWITCH[switch["name"]]

        return CoverMirrorAction.COVER_MIRROR_DEFAULT_ACTION
