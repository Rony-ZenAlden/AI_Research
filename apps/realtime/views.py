from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .publisher import publish_to_user


class TestPingView(APIView):
    """POST /api/v1/realtime/test-ping/ — push a ping to the caller's WS connections."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        message = (request.data.get("message") or "hello from django").strip()[:500]
        delivered = publish_to_user(
            user_id=request.user.id,
            event_type="test.ping",
            data={"message": message},
        )
        return Response(
            {
                "published": True,
                "subscribers_notified": delivered,
                "channel": f"user:{request.user.id}",
            }
        )
