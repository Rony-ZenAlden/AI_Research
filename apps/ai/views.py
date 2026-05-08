from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .providers import (
    LLMAuthError,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
)
from .serializers import SummarizeRequestSerializer
from .services import synthesize


class SummarizeView(APIView):
    """POST /api/v1/ai/summarize/

    Body:
        query    (str)         — the original user question
        mode     ("summarize" | "compare", default "summarize")
        sources  (list)        — what to ground on. Each: {title, ref?, text}

    Returns:
        text, mode, model, provider, duration_ms, sources (with positional indexes)
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SummarizeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = synthesize(
                query=data["query"],
                mode=data.get("mode", "summarize"),
                sources=list(data["sources"]),
            )
        except LLMNotConfiguredError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except LLMAuthError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except LLMRateLimitError as e:
            return Response({"error": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except LLMError as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(result, status=status.HTTP_200_OK)
