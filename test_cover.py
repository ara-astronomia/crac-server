# test_cover.py
from crac_server.component.cover_mirror import COVER_MIRROR

status = COVER_MIRROR.get_status()
print(f"Status: {status}")