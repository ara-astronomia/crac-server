from concurrent import futures
from generated.roof_pb2 import (
    RoofAction,
    RoofStatus,
    RoofResponse,
)
from generated.roof_pb2_grpc import (
    RoofServicer,
    add_RoofServicer_to_server,
)
import grpc

class RoofService(RoofServicer):
    def SetAction(self, request, context):
        
        if request.action == RoofAction.OPEN:
            status = RoofStatus.ROOF_OPENED
        elif request.action == RoofAction.CLOSE:
            status = RoofStatus.ROOF_CLOSED
        else:
            status = RoofStatus.ROOF_CLOSED

        print(status)

        return RoofResponse(status=status)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_RoofServicer_to_server(
        RoofService(), server
    )
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()


# from generated.roof_pb2 import *
# from generated.roof_pb2_grpc import *
# import grpc
# channel = grpc.insecure_channel("localhost:50051")
# client = RoofStub(channel)
# request = RoofRequest(action=RoofAction.OPEN)
# client.SetAction(request)