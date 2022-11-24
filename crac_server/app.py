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


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
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
    server.add_insecure_port(
        f'{Config.getValue("loopback_ip", "server")}:{Config.getValue("port", "server")}')
    server.start()
    logger.info(f'Server loaded on port {Config.getValue("port", "server")}')

    def handle_sigterm(*_):
        logger.info("Received shutdown signal")
        all_rpcs_done_event = server.stop(30)
        all_rpcs_done_event.wait(30)
        logger.info("Shut down gracefully")

    signal(SIGTERM, handle_sigterm)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
