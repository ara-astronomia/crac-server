import logging
from crac_protobuf.telescope_pb2_grpc import TelescopeServicer
from crac_server.converter.telescope_converter import TelescopeMediator
from crac_server.handler.telescope_handler import (
    TelescopeAutolightHandler, 
    TelescopeConnectHandler, 
    TelescopeDisconnectHandler, 
    TelescopeDisconnectedHandler, 
    TelescopeFlatHandler, 
    TelescopeFlatterHandler, 
    TelescopeParkHandler, 
    TelescopeSwitchHandler, 
    TelescopeSyncHandler
)


logger = logging.getLogger(__name__)


class TelescopeService(TelescopeServicer):
    def SetAction(self, request, context):
        logger.debug("TelescopeRequest TelescopeService" + str(request))
        telescope_mediator = TelescopeMediator(request)

        telescope_switch_handler = TelescopeSwitchHandler()
        telescope_connect_handler = TelescopeConnectHandler()
        telescope_disconnected_handler = TelescopeDisconnectedHandler()
        telescope_disconnect_handler = TelescopeDisconnectHandler()
        telescope_sync_handler = TelescopeSyncHandler()
        telescope_park_handler = TelescopeParkHandler()
        telescope_flat_handler = TelescopeFlatHandler()
        telescope_flatter_handler = TelescopeFlatterHandler()
        telescope_autolight_handler = TelescopeAutolightHandler()
        telescope_switch_handler.set_next(telescope_connect_handler) \
            .set_next(telescope_disconnected_handler) \
            .set_next(telescope_disconnect_handler) \
            .set_next(telescope_sync_handler) \
            .set_next(telescope_park_handler) \
            .set_next(telescope_flat_handler) \
            .set_next(telescope_flatter_handler) \
            .set_next(telescope_autolight_handler)
        
        return telescope_switch_handler.handle(telescope_mediator)
