import contextlib
from datetime import timedelta
import logging
import logging.config
import multiprocessing
import os
import socket
import sys
import time

from crac_server.component.camera import get_camera


logging.config.fileConfig('logging.conf')


from signal import signal, SIGTERM
from concurrent import futures
from crac_server.config import Config
from crac_server.service.button_service import ButtonService
from crac_server.service.camera_service import CameraService
from crac_server.service.curtains_service import CurtainsService
from crac_server.service.roof_service import RoofService
from crac_server.service.telescope_service import TelescopeService
from crac_protobuf.button_pb2_grpc import add_ButtonServicer_to_server
from crac_protobuf.camera_pb2_grpc import add_CameraServicer_to_server
from crac_protobuf.curtains_pb2_grpc import add_CurtainServicer_to_server
from crac_protobuf.roof_pb2_grpc import add_RoofServicer_to_server
from crac_protobuf.telescope_pb2_grpc import add_TelescopeServicer_to_server
import grpc


logger = logging.getLogger('crac_server.app')
_ONE_DAY = timedelta(days=1)
_PROCESS_COUNT = multiprocessing.cpu_count()
_THREAD_CONCURRENCY = _PROCESS_COUNT


def _wait_forever(server):
    try:
        while True:
            time.sleep(_ONE_DAY.total_seconds())
    except KeyboardInterrupt:
        server.stop(None)


def _run_server(bind_address, camera):
    """Start a server in a subprocess."""
    logger.info('Starting new server.')
    options = (('grpc.so_reuseport', 1),)

    # WARNING: This example takes advantage of SO_REUSEPORT. Due to the
    # limitations of manylinux1, none of our precompiled Linux wheels currently
    # support this option. (https://github.com/grpc/grpc/issues/18210). To take
    # advantage of this feature, install from source with
    # `pip install grpcio --no-binary grpcio`.

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=2,),
        options=options
    )

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
    add_CameraServicer_to_server(
        CameraService(camera), server
    )

    server.add_insecure_port(bind_address)
    server.start()
    logger.debug(f"Pid in use server is: {os.getpid()}")
    _wait_forever(server)

@contextlib.contextmanager
def _reserve_port():
    """Find and reserve a port for all subprocesses to use."""

    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    if sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT) == 0:
        raise RuntimeError("Failed to set SO_REUSEPORT.")
    sock.bind(('', Config.getInt("port", "server")))
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()

def main():
    with _reserve_port() as port:
        bind_address = 'localhost:{}'.format(port)
        logger.info("Binding to '%s'", bind_address)
        sys.stdout.flush()
        workers = []
        camera = {
            "camera1": get_camera(Config.get_section("camera1")),
            "camera2": get_camera(Config.get_section("camera2")),
        }
        for _ in range(_PROCESS_COUNT):
            # NOTE: It is imperative that the worker subprocesses be forked before
            # any gRPC servers start up. See
            # https://github.com/grpc/grpc/issues/16001 for more details.
            worker = multiprocessing.Process(
                target=_run_server, args=(bind_address,camera,)
            )
            workers.append(worker)
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

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
    server.add_insecure_port(f'{Config.getValue("loopback_ip", "server")}:{Config.getValue("port", "server")}')
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
    logger.info(f"number of processes: {_PROCESS_COUNT}")
    main()
