from crac_protobuf.button_pb2 import (
    ButtonColor,  # type: ignore
    ButtonGui,  # type: ignore
    ButtonKey,  # type: ignore
    ButtonLabel,  # type: ignore
)
from crac_protobuf.roof_pb2 import (
    RoofAction,  # type: ignore
    RoofRequest,  # type: ignore
    RoofResponse,  # type: ignore
    RoofStatus,  # type: ignore
)

from crac_server.component.roof import ROOF
from crac_server.component.roof.roof_control import RoofControl

class RoofMediator:
    def __init__(self, request: RoofRequest) -> None:
        self.request = request
        self._action = request.action
        self._button = ROOF
        self._status = self.button.get_status()
        self._is_disabled = False
    
    
    @property
    def action(self) -> RoofAction:
        return self._action

    @property
    def button(self) -> RoofControl:
        return self._button

    @property
    def status(self) -> RoofStatus:
        return self._status
    
    @status.setter
    def status(self, value: RoofStatus):
        self._status = value

    @property
    def is_disabled(self) -> bool:
        return self._is_disabled
    
    @is_disabled.setter
    def is_disabled(self, value: bool):
        self._is_disabled = value

class RoofConverter:
    def convert(self, mediator: RoofMediator) -> RoofResponse:
        if mediator.status in [RoofStatus.ROOF_OPENED]:
            text_color, background_color = ("white", "green")
        else:
            text_color, background_color = ("white", "red")

        label = self.__roof_label(mediator.status)

        button_gui = ButtonGui(
            key=ButtonKey.KEY_ROOF,
            label=label,
            metadata=(RoofAction.CLOSE if mediator.status in [RoofStatus.ROOF_OPENED, RoofStatus.ROOF_OPENING] else RoofAction.OPEN),
            is_disabled=mediator.is_disabled,
            button_color=ButtonColor(text_color=text_color, background_color=background_color),
        )

        return RoofResponse(status=mediator.status, button_gui=button_gui)

    def __roof_label(self, status):
        label = None
        if status is RoofStatus.ROOF_CLOSED:
            label = ButtonLabel.LABEL_CLOSE
        elif status is RoofStatus.ROOF_OPENED:
            label = ButtonLabel.LABEL_OPEN
        elif status is RoofStatus.ROOF_CLOSING:
            label = ButtonLabel.LABEL_CLOSING
        elif status is RoofStatus.ROOF_OPENING:
            label = ButtonLabel.LABEL_OPENING
        return label

    # TODO use this after upgrading to python >= 3.10
    # def __roof_label310(self, status):
    #     match status:
    #         case RoofStatus.ROOF_CLOSED:
    #             label = ButtonLabel.LABEL_CLOSE
    #         case RoofStatus.ROOF_OPENED:
    #             label = ButtonLabel.LABEL_OPEN
    #         case RoofStatus.ROOF_CLOSING:
    #             label = ButtonLabel.LABEL_CLOSING
    #         case RoofStatus.ROOF_OPENING:
    #             label = ButtonLabel.LABEL_OPENING
    #     return label