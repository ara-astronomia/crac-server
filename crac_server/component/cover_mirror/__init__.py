import asyncio
from crac_server.component.cover_mirror.cover_mirror_control import CoverMirrorControl

COVER_MIRROR: CoverMirrorControl = CoverMirrorControl()
# Avvia polling asincrono quando il modulo viene importato
try:
    asyncio.create_task(COVER_MIRROR.get_status())
except RuntimeError:
    # Se non c'è un event loop attivo, verrà avviato dopo
    pass