import logging
from crac_protobuf.cover_mirror_pb2 import (
    CoverMirrorRequest,  # type: ignore
    CoverMirrorResponse,  # type: ignore
)
from crac_protobuf.cover_mirror_pb2_grpc import CoverMirrorServicer  # type: ignore
from crac_server.converter.cover_mirror_converter import CoverMirrorMediator
from crac_server.handler.cover_mirror_handler import (
    CoverMirrorHandler,
    CoverMirrorSwitchHandler,
)

logger = logging.getLogger(__name__)


class CoverMirrorService(CoverMirrorServicer):
    async def SetAction(self, request: CoverMirrorRequest, context) -> CoverMirrorResponse:
        logger.debug("Request " + str(request))
        cover_mirror_mediator = CoverMirrorMediator(request)
        switch_handler = CoverMirrorSwitchHandler()
        cover_mirror_handler = CoverMirrorHandler()
        switch_handler._next_handler = cover_mirror_handler
        return switch_handler.handle(cover_mirror_mediator)