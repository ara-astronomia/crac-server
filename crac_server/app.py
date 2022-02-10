import logging
import logging.config


logging.config.fileConfig('logging.conf')


from gpiozero import Device
from gpiozero.pins.mock import MockFactory
if Device.pin_factory is not None:
    Device.pin_factory.reset()
Device.pin_factory = MockFactory()


from signal import signal, SIGTERM
from concurrent import futures
from crac_protobuf.button_pb2_grpc import add_ButtonServicer_to_server
from crac_protobuf.curtains_pb2_grpc import add_CurtainServicer_to_server
from crac_protobuf.roof_pb2_grpc import add_RoofServicer_to_server
from crac_protobuf.telescope_pb2_grpc import add_TelescopeServicer_to_server
import grpc
from crac_server.service.button_service import ButtonService
from crac_server.service.curtains_service import CurtainsService
from crac_server.service.roof_service import RoofService
from crac_server.service.telescope_service import TelescopeService



logger = logging.getLogger('crac_server.app')


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
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
    server.add_insecure_port("[::]:50051")
    server.start()
    logger.info("Server loaded")

    def handle_sigterm(*_):
        logger.info("Received shutdown signal")
        all_rpcs_done_event = server.stop(30)
        all_rpcs_done_event.wait(30)
        logger.info("Shut down gracefully")

    signal(SIGTERM, handle_sigterm)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
