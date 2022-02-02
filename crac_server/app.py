from signal import signal, SIGTERM
from concurrent import futures
from tkinter import Button
from crac_protobuf.button_pb2_grpc import add_ButtonServicer_to_server
from crac_protobuf.roof_pb2_grpc import add_RoofServicer_to_server
import grpc
from crac_server.logger import Logger
from crac_server.service.button_service import ButtonService
from crac_server.service.roof_service import RoofService
from gpiozero import Device
from gpiozero.pins.mock import MockFactory
if Device.pin_factory is not None:
    Device.pin_factory.reset()
Device.pin_factory = MockFactory()


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_RoofServicer_to_server(
        RoofService(), server
    )
    add_ButtonServicer_to_server(
        ButtonService(), server
    )
    server.add_insecure_port("[::]:50051")
    server.start()

    def handle_sigterm(*_):
        print("Received shutdown signal")
        all_rpcs_done_event = server.stop(30)
        all_rpcs_done_event.wait(30)
        print("Shut down gracefully")

    signal(SIGTERM, handle_sigterm)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
