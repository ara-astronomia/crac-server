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
    ButtonStatus,   # type: ignore
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
    async def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if self._next_handler:
            return await self._next_handler.handle(mediator)
        
        return ButtonConverter().convert(mediator)


class ButtonWeatherHandler(AbstractButtonHandler):
    async def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        logger.debug("In weather handler")
        if (
            mediator.status is ButtonStatus.OFF and 
            mediator.type == ButtonType.TELE_SWITCH
        ):
            logger.debug(f"In turn on or check action {mediator.action} for {mediator.type}")
            weather_converter = WeatherConverter()
            weather_response = weather_converter.convert(WEATHER)
            logger.debug(f"In weather status {weather_response.status}")
            if weather_response.status == WeatherStatus.WEATHER_STATUS_DANGER:
                logger.info(f"In status danger {weather_response.status}")
                mediator.is_disabled = True
                self._next_handler = None

        return await super().handle(mediator)


class ButtonTelescopeHandler(AbstractButtonHandler):
    async def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if (
            mediator.type == ButtonType.TELE_SWITCH and
            mediator.action == ButtonAction.TURN_OFF
        ):
            logger.debug("Turned off telescope connection when telescope is turned off")
            TELESCOPE.polling_end()

        return await super().handle(mediator)


class ButtonFlatHandler(AbstractButtonHandler):
    async def handle(self, mediator: ButtonMediator) -> ButtonResponse:
        if (
            mediator.type == ButtonType.FLAT_LIGHT and
            mediator.action is ButtonAction.TURN_ON and
            TELESCOPE.status is TelescopeStatus.FLATTER
        ):
            logger.debug("Track telescope on when Flat Panel is switched on")
            TELESCOPE.queue_set_speed(TelescopeSpeed.SPEED_TRACKING)

        return await super().handle(mediator)


class ButtonActionHandler(AbstractButtonHandler):
    async def handle(self, mediator: ButtonMediator) -> ButtonResponse:         
        if mediator.action == ButtonAction.TURN_ON:
            await mediator.button.on()
            self._next_handler = None
        elif mediator.action == ButtonAction.TURN_OFF:
            await mediator.button.off()
            self._next_handler = None

        return await super().handle(mediator)
