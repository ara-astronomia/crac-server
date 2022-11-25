import logging
from crac_server.component.telescope import TELESCOPE
from crac_server.component.weather import WEATHER
from crac_server.converter.button_converter import (
    ButtonConverter, 
    ButtonMediator,
)
from crac_server.converter.weather_converter import WeatherConverter
from crac_server.handler.handler import AbstractHandler
from crac_protobuf.button_pb2 import (
    ButtonAction,  # type: ignore
    ButtonType,  # type: ignore
    ButtonResponse,  # type: ignore
    ButtonStatus,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeSpeed,  # type: ignore
    TelescopeStatus,  # type: ignore
)
from crac_protobuf.chart_pb2 import (
    WeatherStatus,  # type: ignore
)


logger = logging.getLogger(__name__)


class AbstractButtonHandler(AbstractHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if self._next_handler:
            return self._next_handler.handle(mediator)
        
        return ButtonConverter().convert(mediator)


class ButtonWeatherHandler(AbstractButtonHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        logger.info("In weather handler")
        if (
            mediator.action in (ButtonAction.TURN_ON, ButtonAction.CHECK_BUTTON) and 
            mediator.type == ButtonType.TELE_SWITCH
        ):
            logger.info(f"In turn on or check action {mediator.action} for {mediator.type}")
            weather_converter = WeatherConverter()
            weather_response = weather_converter.convert(WEATHER)
            logger.info(f"In weather status {weather_response.status}")
            if weather_response.status == WeatherStatus.WEATHER_STATUS_DANGER:
                logger.info(f"In status danger {weather_response.status}")
                mediator.is_disabled = True
                self._next_handler = None

        return super().handle(mediator)

class ButtonActionHandler(AbstractButtonHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:         
        if mediator.action == ButtonAction.TURN_ON:
            mediator.button.on()
            self._next_handler = None
        elif mediator.action == ButtonAction.TURN_OFF:
            mediator.button.off()
            self._next_handler = None

        return super().handle(mediator)


class ButtonTelescopeHandler(AbstractButtonHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if (
            mediator.type == ButtonType.TELE_SWITCH and
            mediator.action == ButtonAction.TURN_OFF
        ):
            mediator.button.off()
            logger.debug("Turned off telescope connection when telescope is turned off")
            TELESCOPE.polling_end()
            self._next_handler = None

        return super().handle(mediator)


class ButtonFlatHandler(AbstractButtonHandler):
    def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if (
            mediator.type == ButtonType.FLAT_LIGHT and
            mediator.status is ButtonStatus.ON and
            TELESCOPE.status is TelescopeStatus.FLATTER
        ):
            mediator.button.on()
            logger.debug("Track telescope on when Flat Panel is switched on")
            TELESCOPE.queue_set_speed(TelescopeSpeed.SPEED_TRACKING)
            self._next_handler = None

        return super().handle(mediator)
