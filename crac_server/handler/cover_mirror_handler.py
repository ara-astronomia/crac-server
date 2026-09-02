import asyncio
import logging
from crac_protobuf.cover_mirror_pb2 import (
    CoverMirrorAction,  # type: ignore
    CoverMirrorResponse,  # type: ignore
    CoverMirrorStatus,  # type: ignore
)
from crac_server.converter.cover_mirror_converter import (
    CoverMirrorConverter,
    CoverMirrorMediator,
)
from crac_server.handler.handler import AbstractHandler

logger = logging.getLogger(__name__)

# Keep strong references so fire-and-forget tasks are not garbage-collected
# while still pending (see https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task)
_background_tasks: set = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class AbstractCoverMirrorHandler(AbstractHandler):
    def handle(self, mediator: CoverMirrorMediator) -> CoverMirrorResponse:
        if self._next_handler:
            return self._next_handler.handle(mediator)
        return CoverMirrorConverter().convert(mediator)


class CoverMirrorHandler(AbstractCoverMirrorHandler):
    def handle(self, mediator: CoverMirrorMediator) -> CoverMirrorResponse:
        if mediator.status in [CoverMirrorStatus.COVER_MIRROR_OPENING, CoverMirrorStatus.COVER_MIRROR_CLOSING]:
            self._next_handler = None
            mediator.is_disabled = True
        elif mediator.action is CoverMirrorAction.OPEN_COVER_MIRROR:
            _spawn(mediator.button.open())
        elif mediator.action is CoverMirrorAction.CLOSE_COVER_MIRROR:
            _spawn(mediator.button.close())

        return super().handle(mediator)