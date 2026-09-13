from functools import lru_cache

from crac_server.component.cover_mirror.cover_mirror_control import CoverMirrorControl


@lru_cache(maxsize=1)
def cover_mirror() -> CoverMirrorControl:
    return CoverMirrorControl()
