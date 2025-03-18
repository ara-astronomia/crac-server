import logging
import logging.config


logging.config.fileConfig('logging.conf')

from crac_protobuf.ups_pb2_grpc import add_UpsServicer_to_server
from crac_protobuf.chart_pb2_grpc import add_WeatherServicer_to_server
from crac_protobuf.telescope_pb2_grpc import add_TelescopeServicer_to_server
from crac_protobuf.roof_pb2_grpc import add_RoofServicer_to_server
from crac_protobuf.curtains_pb2_grpc import add_CurtainServicer_to_server
from crac_protobuf.button_pb2_grpc import add_ButtonServicer_to_server
from crac_server.service.weather_service import WeatherService
from crac_server.service.telescope_service import TelescopeService
from crac_server.service.roof_service import RoofService
from crac_server.service.curtains_service import CurtainsService
from crac_server.service.button_service import ButtonService
from crac_server.service.curtains_service import CurtainsService
from crac_server.service.roof_service import RoofService
from crac_server.service.telescope_service import TelescopeService
from crac_server.service.ups_service import UpsService
from crac_server.service.weather_service import WeatherService
from crac_server.config import Config
import asyncio
import grpc


logger = logging.getLogger('crac_server.app')


async def serve():
    server = grpc.aio.server()
    add_ButtonServicer_to_server(
        ButtonService(), server
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
    add_UpsServicer_to_server(
        UpsService(), server
    )
    server.add_insecure_port(
        f'{Config.getValue("loopback_ip", "server")}:{Config.getValue("port", "server")}')
    logger.info(f'Server loaded on port {Config.getValue("port", "server")}')
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
