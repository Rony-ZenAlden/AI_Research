"""
ASGI config — boots Django HTTP + Channels WebSocket router.
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "NeuroSeek_AI.settings.dev")
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

# Phase 1: HTTP only. WebSocket routes are added in Phase 2 once consumers exist.
websocket_urlpatterns: list = []

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
    }
)
