import asyncio
import logging
import logging.config
logging.config.fileConfig('logging.conf')

from crac_protobuf.chart_pb2_grpc import add_WeatherServicer_to_server
from crac_protobuf.telescope_pb2_grpc import add_TelescopeServicer_to_server
from crac_protobuf.roof_pb2_grpc import add_RoofServicer_to_server
from crac_protobuf.curtains_pb2_grpc import add_CurtainServicer_to_server
from crac_protobuf.camera_pb2_grpc import add_CameraServicer_to_server
from crac_protobuf.button_pb2_grpc import add_ButtonServicer_to_server
from crac_server.service.weather_service import WeatherService
from crac_server.service.telescope_service import TelescopeService
from crac_server.service.roof_service import RoofService
from crac_server.service.curtains_service import CurtainsService
from crac_server.service.camera_service import CameraService
from crac_server.service.button_service import ButtonService
from crac_server.config import Config
from concurrent import futures
import grpc
from signal import signal, SIGTERM


logger = logging.getLogger('crac_server.app')
# Coroutines to be invoked when the event loop is shutting down.
_cleanup_coroutines = []


async def serve():
    server = grpc.aio.server()
    add_ButtonServicer_to_server(
        ButtonService(), server
    )
    add_CameraServicer_to_server(
        CameraService(), server
    )
    add_CurtainServicer_to_server(
        CurtainsService(), server
    )
    add_RoofServicer_to_server(
        RoofService(), server
    )
    add_TelescopeServicer_to_server(
        TelescopeService(), server
    )
    add_WeatherServicer_to_server(
        WeatherService(), server
    )
    server.add_insecure_port(f'{Config.getValue("loopback_ip", "server")}:{Config.getValue("port", "server")}')
    await server.start()
    logger.info(f'Server loaded on port {Config.getValue("port", "server")}')

    async def server_graceful_shutdown():
        logging.info("Starting graceful shutdown...")
        # Shuts down the server with 5 seconds of grace period. During the
        # grace period, the server won't accept new connections and allow
        # existing RPCs to continue within the grace period.
        await server.stop(5)
    
    _cleanup_coroutines.append(server_graceful_shutdown())
    await server.wait_for_termination()


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(serve())
    finally:
        loop.run_until_complete(*_cleanup_coroutines)
        loop.close()