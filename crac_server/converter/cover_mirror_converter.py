from crac_protobuf.button_pb2 import (
    ButtonColor,  # type: ignore
    ButtonGui,  # type: ignore
    ButtonKey,  # type: ignore
    ButtonLabel,  # type: ignore
)
from crac_protobuf.cover_mirror_pb2 import (
    CoverMirrorAction,  # type: ignore
    CoverMirrorRequest,  # type: ignore
    CoverMirrorResponse,  # type: ignore
    CoverMirrorStatus,  # type: ignore
)
from crac_server.component.cover_mirror import COVER_MIRROR
from crac_server.component.cover_mirror.cover_mirror_control import CoverMirrorControl


class CoverMirrorMediator:
    def __init__(self, request: CoverMirrorRequest) -> None:
        self.request = request
        self._action = request.action
        self._button = COVER_MIRROR
        self._status = self.button.get_status()
        self._is_disabled = False

    @property
    def action(self) -> CoverMirrorAction:
        return self._action

    @property
    def button(self) -> CoverMirrorControl:
        return self._button

    @property
    def status(self) -> CoverMirrorStatus:
        return self._status

    @status.setter
    def status(self, value: CoverMirrorStatus):
        self._status = value

    @property
    def is_disabled(self) -> bool:
        return self._is_disabled

    @is_disabled.setter
    def is_disabled(self, value: bool):
        self._is_disabled = value


class CoverMirrorConverter:
    def convert(self, mediator: CoverMirrorMediator) -> CoverMirrorResponse:
        if mediator.status is CoverMirrorStatus.COVER_MIRROR_OPENED:
            text_color, background_color = ("white", "green")
        else:
            text_color, background_color = ("white", "red")

        label = self.__cover_mirror_label(mediator.status)

        button_gui = ButtonGui(
            key=ButtonKey.KEY_COVER_MIRROR,
            label=label,
            metadata=(
                CoverMirrorAction.CLOSE_COVER_MIRROR
                if mediator.status in [CoverMirrorStatus.COVER_MIRROR_OPENED, CoverMirrorStatus.COVER_MIRROR_OPENING]
                else CoverMirrorAction.OPEN_COVER_MIRROR
            ),
            is_disabled=mediator.is_disabled,
            button_color=ButtonColor(text_color=text_color, background_color=background_color),
        )

        return CoverMirrorResponse(status=mediator.status, button_gui=button_gui)

    def __cover_mirror_label(self, status):
        if status is CoverMirrorStatus.COVER_MIRROR_CLOSED:
            return ButtonLabel.LABEL_CLOSE
        elif status is CoverMirrorStatus.COVER_MIRROR_OPENED:
            return ButtonLabel.LABEL_OPEN
        elif status is CoverMirrorStatus.COVER_MIRROR_CLOSING:
            return ButtonLabel.LABEL_CLOSING
        elif status is CoverMirrorStatus.COVER_MIRROR_OPENING:
            return ButtonLabel.LABEL_OPENING
        elif status is CoverMirrorStatus.COVER_MIRROR_ERROR:
            return ButtonLabel.LABEL_ERROR
        return ButtonLabel.LABEL_ERROR