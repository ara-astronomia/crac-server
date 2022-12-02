import logging
from threading import Lock, Thread
from time import sleep
from crac_protobuf.button_pb2 import (
    ButtonType,  # type: ignore
)
from crac_protobuf.chart_pb2_grpc import WeatherServicer
from crac_protobuf.chart_pb2 import (
    WeatherRequest,  # type: ignore
    WeatherResponse,  # type: ignore
    WeatherStatus,  # type: ignore
)
from crac_protobuf.curtains_pb2 import (
    CurtainStatus,  # type: ignore
)
from crac_protobuf.telescope_pb2 import (
    TelescopeSpeed,  # type: ignore
    TelescopeStatus,  # type: ignore
)
from crac_server.component.button_control import SWITCHES
from crac_server.component.curtains.factory_curtain import CURTAIN_EAST, CURTAIN_WEST
from crac_server.component.roof import ROOF
from crac_server.component.telescope import TELESCOPE
from crac_server.component.weather import WEATHER
from crac_server.converter.weather_converter import WeatherConverter


logger = logging.getLogger(__name__)


class WeatherService(WeatherServicer):

    def __init__(self) -> None:
        self.t = None
        super().__init__()
        self.lock = Lock()

    def GetStatus(self, request: WeatherRequest, context) -> WeatherResponse:
        weather_converter = WeatherConverter()
        response = weather_converter.convert(WEATHER)
        logger.info("weather response")
        logger.info(response)

        if (
            response.status == WeatherStatus.WEATHER_STATUS_DANGER and
            TELESCOPE.polling and 
            self.t == None
        ):
            logger.info("weather in danger status - block crac")
            self.t = Thread(target=self.__emergency_closure)
            self.t.start()
        return response

    def __emergency_closure(self):
        with self.lock:
            logger.info("weather in danger status - send telescope in park")
            TELESCOPE.park(TelescopeSpeed.SPEED_NOT_TRACKING)
            
            while TELESCOPE.status > TelescopeStatus.SECURE:
                logger.info("weather in danger status - waiting for telescope in park")
                sleep(1)
            logger.info(f"weather in danger status - telescope is in status {TELESCOPE.status}")
            
            while CURTAIN_EAST.get_status() in (CurtainStatus.CURTAIN_OPENING, CurtainStatus.CURTAIN_CLOSING):
                sleep(1)
                logger.info(f"weather in danger status - curtain east is in status {CURTAIN_EAST.get_status()}")
            logger.info("weather in danger status - disable east curt")
            CURTAIN_EAST.disable()
        
            while CURTAIN_WEST.get_status() in (CurtainStatus.CURTAIN_OPENING, CurtainStatus.CURTAIN_CLOSING):
                sleep(1)
                logger.info(f"weather in danger status - curtain west is in status {CURTAIN_WEST.get_status()}")
            logger.info("weather in danger status - disable west curt")
            CURTAIN_WEST.disable()
            
            while (
                CURTAIN_EAST.get_status() is not CurtainStatus.CURTAIN_DISABLED or 
                CURTAIN_WEST.get_status() is not CurtainStatus.CURTAIN_DISABLED
            ):
                sleep(1)
            logger.info("weather in danger status - close the roof")
            ROOF.close()
            
            logger.info("weather in danger status - switch off telescope button")
            TELESCOPE.polling_end()
            SWITCHES[ButtonType.Name(ButtonType.TELE_SWITCH)].off()
            self.t = None