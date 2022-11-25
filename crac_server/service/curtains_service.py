import logging
from crac_protobuf.curtains_pb2_grpc import CurtainServicer
from crac_server.converter.curtains_converter import CurtainsMediator
from crac_server.handler.curtains_handler import CurtainsCalibrationHandler, CurtainsDisableHandler, CurtainsEnableHandler, CurtainsMoveHandler, CurtainsRoofHandler, CurtainsTelescopeHandler, CurtainsWeatherHandler


logger = logging.getLogger(__name__)


class CurtainsService(CurtainServicer):
    def SetAction(self, request, context):
        logger.debug("Request " + str(request))
        curtains_mediator = CurtainsMediator(request)

        roof_curtains_handler = CurtainsRoofHandler()
        weather_curtains_handler = CurtainsWeatherHandler()
        telescope_curtains_handler = CurtainsTelescopeHandler()
        disable_curtains_handler = CurtainsDisableHandler()
        enable_curtains_handelr = CurtainsEnableHandler()
        calibration_curtains_handler = CurtainsCalibrationHandler()
        move_curtains_handler = CurtainsMoveHandler()
        roof_curtains_handler.set_next(weather_curtains_handler).set_next(telescope_curtains_handler).set_next(disable_curtains_handler).set_next(enable_curtains_handelr).set_next(calibration_curtains_handler).set_next(move_curtains_handler)

        return roof_curtains_handler.handle(curtains_mediator)
