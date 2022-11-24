from crac_protobuf.button_pb2 import (
    ButtonAction,  # type: ignore
    ButtonColor,  # type: ignore
    ButtonGui,  # type: ignore
    ButtonKey,  # type: ignore
    ButtonLabel,  # type: ignore
    ButtonRequest,  # type: ignore
    ButtonResponse,  # type: ignore
    ButtonStatus,  # type: ignore
    ButtonType,  # type: ignore
)

from crac_server.component.button_control import SWITCHES, ButtonControl


class ButtonMediator:
    def __init__(self, request: ButtonRequest) -> None:
        self.request = request
        self._type = request.type
        self._action = request.action
        self._button = SWITCHES[ButtonType.Name(request.type)]
        self._status = self.button.get_status()
        self._is_disabled = False
    
    @property
    def type(self) -> ButtonType:
        return self._type
    
    @property
    def action(self) -> ButtonAction:
        return self._action

    @property
    def button(self) -> ButtonControl:
        return self._button

    @property
    def status(self) -> ButtonStatus:
        return self._status
    
    @status.setter
    def status(self, value: ButtonStatus):
        self._status = value

    @property
    def is_disabled(self) -> bool:
        return self._is_disabled
    
    @is_disabled.setter
    def is_disabled(self, value: bool):
        self._is_disabled = value
    

class ButtonConverter:
    def convert(self, button_mediator: ButtonMediator) -> ButtonResponse:
        if button_mediator.status is ButtonStatus.ON:
            text_color, background_color = ("white", "green")
        else:
            text_color, background_color = ("white", "red")
    
        button_gui = ButtonGui(
            key=ButtonKey.Value(f"KEY_{ButtonType.Name(button_mediator.type)}"),
            label=(ButtonLabel.LABEL_ON if button_mediator.status is ButtonStatus.ON else ButtonLabel.LABEL_OFF),
            metadata=(ButtonAction.TURN_OFF if button_mediator.status is ButtonStatus.ON else ButtonAction.TURN_ON),
            is_disabled=button_mediator.is_disabled,
            button_color=ButtonColor(text_color=text_color, background_color=background_color),
        )

        return ButtonResponse(
            status=button_mediator.status, 
            type=button_mediator.type, 
            button_gui=button_gui
        )
