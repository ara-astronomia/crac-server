import logging
from crac_protobuf.button_pb2 import (
    ButtonColor,  # type: ignore
    ButtonGui,  # type: ignore
    ButtonKey,  # type: ignore
    ButtonLabel,  # type: ignore
)
from crac_protobuf.curtains_pb2 import (
    CurtainOrientation,  # type: ignore
    CurtainEntryResponse,  # type: ignore
    CurtainsAction,  # type: ignore
    CurtainsRequest,  # type: ignore
    CurtainsResponse,  # type: ignore
    CurtainStatus,  # type: ignore
)
from crac_server.component.curtains.curtains import Curtain
from crac_server.component.curtains.factory_curtain import (
    CURTAIN_EAST,
    CURTAIN_WEST,
)


logger = logging.getLogger(__name__)


class CurtainsMediator:
    def __init__(self, request: CurtainsRequest) -> None:
        self.request = request
        self._action = request.action
        self._button_east = CURTAIN_EAST
        self._button_west = CURTAIN_WEST
        self._status_east = self.button_east.get_status()
        self._status_west = self.button_west.get_status()
        self._steps_east = self.button_east.steps()
        self._steps_west = self.button_west.steps()
        self._is_disabled = False

    @property
    def action(self) -> CurtainsAction:
        return self._action

    @property
    def button_east(self) -> Curtain:
        return self._button_east

    @property
    def button_west(self) -> Curtain:
        return self._button_west

    @property
    def status_east(self) -> CurtainStatus:
        return self._status_east

    @property
    def status_west(self) -> CurtainStatus:
        return self._status_west

    @property
    def steps_east(self) -> int:
        return self._steps_east

    @property
    def steps_west(self) -> int:
        return self._steps_west

    @property
    def is_disabled(self) -> bool:
        return self._is_disabled
    
    @is_disabled.setter
    def is_disabled(self, value: bool):
        self._is_disabled = value


class CurtainsConverter:
    def convert(self, mediator: CurtainsMediator) -> CurtainsResponse:
        curtain_east_entry = CurtainEntryResponse(orientation=CurtainOrientation.CURTAIN_EAST)
        curtain_west_entry = CurtainEntryResponse(orientation=CurtainOrientation.CURTAIN_WEST)
        curtain_east_entry.status = mediator.status_east
        curtain_west_entry.status = mediator.status_west
        curtain_east_entry.steps = mediator.steps_east
        curtain_west_entry.steps = mediator.steps_west
        logger.debug("actual east curtain steps %s", curtain_east_entry.steps)
        logger.debug("actual west curtain steps %s", curtain_west_entry.steps)
        if (
            curtain_east_entry.status is CurtainStatus.CURTAIN_DISABLED and 
            curtain_west_entry.status is CurtainStatus.CURTAIN_DISABLED
        ):
            metadata_enable_button = CurtainsAction.ENABLE
            name_enable_button = ButtonLabel.LABEL_DISABLE
            text_color, background_color = ("white", "red")
        else:
            metadata_enable_button = CurtainsAction.DISABLE
            name_enable_button = ButtonLabel.LABEL_ENABLE
            text_color, background_color = ("white", "green")
            
        enable_button = ButtonGui(
            key=ButtonKey.KEY_CURTAINS,
            label=name_enable_button,
            metadata=metadata_enable_button,
            is_disabled=mediator.is_disabled,
            button_color=ButtonColor(text_color=text_color, background_color=background_color),
        )

        calibrate_button = ButtonGui(
            key=ButtonKey.KEY_CALIBRATE,
            label=ButtonLabel.LABEL_CALIBRATE,
            is_disabled=True,
            metadata=CurtainsAction.CALIBRATE_CURTAINS,
            button_color=ButtonColor(text_color="white", background_color="red"),
        )

        return CurtainsResponse(
            curtains=(
                curtain_east_entry, 
                curtain_west_entry
            ), 
            buttons_gui=[
                enable_button, 
                calibrate_button
            ]
        )
