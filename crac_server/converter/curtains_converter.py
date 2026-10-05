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
    curtain_east,
    curtain_west,
)


logger = logging.getLogger(__name__)


class CurtainsMediator:
    def __init__(self, request: CurtainsRequest) -> None:
        self.request = request
        self._action = request.action
        self._curtain_east = curtain_east()
        self._curtain_west = curtain_west()
        self._status_east = self.curtain_east.get_status()
        self._status_west = self.curtain_west.get_status()
        self._steps_east = self.curtain_east.steps()
        self._steps_west = self.curtain_west.steps()
        self._is_disabled = False

    @property
    def action(self) -> CurtainsAction:
        return self._action

    @property
    def curtain_east(self) -> Curtain:
        return self._curtain_east

    @property
    def curtain_west(self) -> Curtain:
        return self._curtain_west

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
            is_disabled=mediator.is_disabled and metadata_enable_button is CurtainsAction.ENABLE,
            button_color=ButtonColor(text_color=text_color, background_color=background_color),
        )

        return CurtainsResponse(
            curtains=(
                curtain_east_entry, 
                curtain_west_entry
            ), 
            buttons_gui=[enable_button]
        )
