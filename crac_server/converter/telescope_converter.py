import logging
from crac_protobuf.button_pb2 import (
    ButtonKey,  # type: ignore
    ButtonLabel,  # type: ignore
    ButtonColor,  # type: ignore
    ButtonGui,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeAction,  # type: ignore
    TelescopeResponse,  # type: ignore
    TelescopeRequest,  # type: ignore
    TelescopeSpeed,  # type: ignore
    TelescopeStatus,  # type: ignore
)
from crac_server.component.telescope import (
    TELESCOPE, 
    Telescope,
)


logger = logging.getLogger(__name__)


class TelescopeMediator:
    def __init__(self, request: TelescopeRequest) -> None:
        self.request = request
        self._action = request.action
        self._button = TELESCOPE
        self._status = self.button.status
        self._speed = self.button.speed
        self._connect_is_disabled = False
        self._sync_is_disabled = False
        self._park_is_disabled = False
        self._flat_is_disabled = False
    
    
    @property
    def action(self) -> TelescopeAction:
        return self._action

    @property
    def button(self) -> Telescope:
        return self._button

    @property
    def status(self) -> TelescopeStatus:
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def speed(self) -> TelescopeSpeed:
        return self._speed

    @speed.setter
    def speed(self, value):
        self._speed = value

    @property
    def connect_is_disabled(self) -> bool:
        return self._connect_is_disabled
    
    @connect_is_disabled.setter
    def connect_is_disabled(self, value: bool):
        self._connect_is_disabled = value

    @property
    def sync_is_disabled(self) -> bool:
        return self._sync_is_disabled
    
    @sync_is_disabled.setter
    def sync_is_disabled(self, value: bool):
        self._sync_is_disabled = value

    @property
    def park_is_disabled(self) -> bool:
        return self._park_is_disabled
    
    @park_is_disabled.setter
    def park_is_disabled(self, value: bool):
        self._park_is_disabled = value

    @property
    def flat_is_disabled(self) -> bool:
        return self._flat_is_disabled
    
    @flat_is_disabled.setter
    def flat_is_disabled(self, value: bool):
        self._flat_is_disabled = value

class TelescopeConverter:
    def convert(self, mediator: TelescopeMediator) -> TelescopeResponse:
        
        label_connect, metadata_connect = self.__text_metadata_connect_button(mediator.status)
        connection_button_gui = ButtonGui(
            key=ButtonKey.KEY_TELESCOPE_CONNECTION_TOGGLE,
            label=label_connect,
            metadata=metadata_connect,
            button_color=self.__draw_connect_button(mediator.status),
            is_disabled=mediator.connect_is_disabled
        )

        sync_button_gui = ButtonGui(
            key=ButtonKey.KEY_SYNC,
            label=ButtonLabel.LABEL_SYNC,
            metadata=TelescopeAction.SYNC,
            is_disabled=mediator.sync_is_disabled,
            button_color=ButtonColor(text_color="black", background_color="white") if mediator.status < TelescopeStatus.LOST else ButtonColor(text_color="white", background_color="red") 
        )

        park_button_color, flat_button_color = self.__draw_park_flat_buttons(mediator.status)
        park_button_gui = ButtonGui(
            key=ButtonKey.KEY_PARK,
            label=ButtonLabel.LABEL_PARK,
            metadata=TelescopeAction.PARK_POSITION,
            is_disabled=mediator.park_is_disabled,
            button_color=park_button_color
        ) 

        flat_button_gui = ButtonGui(
            key=ButtonKey.KEY_FLAT,
            label=ButtonLabel.LABEL_FLAT,
            metadata=TelescopeAction.FLAT_POSITION,
            is_disabled=mediator.flat_is_disabled,
            button_color=flat_button_color
        )

        return TelescopeResponse(
            status=mediator.status,
            airmass=mediator.button.airmass, 
            aa_coords=mediator.button.aa_coords, 
            eq_coords=mediator.button.eq_coords,
            speed=mediator.speed, 
            buttons_gui=[
                connection_button_gui,
                sync_button_gui,
                park_button_gui,
                flat_button_gui,
            ]
        )

    def __draw_connect_button(self, status):
        if status < TelescopeStatus.LOST:
            text_color = "white"
            background_color = "green"
        elif status in (TelescopeStatus.LOST, TelescopeStatus.DISCONNECTED):
            text_color = "white"
            background_color = "red"
        else:
            text_color = "white"
            background_color = "orange"

        return ButtonColor(text_color=text_color, background_color=background_color)
    
    def __text_metadata_connect_button(self, status):
        if status < TelescopeStatus.LOST:
            label = ButtonLabel.LABEL_TELESCOPE_CONNECTED
            metadata = TelescopeAction.TELESCOPE_DISCONNECT
        else:
            label = ButtonLabel.LABEL_TELESCOPE_DISCONNECTED
            metadata = TelescopeAction.TELESCOPE_CONNECT
        return label, metadata

    def __draw_park_flat_buttons(self, status):
        if status is TelescopeStatus.PARKED:
            park_button_color = ButtonColor(text_color="white", background_color="green")
            flat_button_color = ButtonColor(text_color="black", background_color="white")
        elif status is TelescopeStatus.FLATTER:
            park_button_color = ButtonColor(text_color="black", background_color="white")
            flat_button_color = ButtonColor(text_color="white", background_color="green")
        elif status >= TelescopeStatus.LOST:
            park_button_color = ButtonColor(text_color="white", background_color="red")
            flat_button_color = ButtonColor(text_color="white", background_color="red")
        else:
            park_button_color = ButtonColor(text_color="black", background_color="white")
            flat_button_color = ButtonColor(text_color="black", background_color="white")
        return park_button_color, flat_button_color

    # def __draw_park_flat_buttons310(self, status):
    #     match status:
    #         case TelescopeStatus.PARKED:
    #             park_button_color = ButtonColor(text_color="white", background_color="green")
    #             flat_button_color = ButtonColor(text_color="black", background_color="white")
    #         case TelescopeStatus.FLATTER:
    #             park_button_color = ButtonColor(text_color="black", background_color="white")
    #             flat_button_color = ButtonColor(text_color="white", background_color="green")
    #         case _:
    #             park_button_color = ButtonColor(text_color="black", background_color="white")
    #             flat_button_color = ButtonColor(text_color="black", background_color="white")
    #     return park_button_color,flat_button_color
