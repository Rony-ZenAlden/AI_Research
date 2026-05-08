import time

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.queries.services import record_search
from apps.vector.models import Document
from apps.vector.serializers import DocumentDetailSerializer

from .searxng import SearXNGClient, SearXNGError
from .serializers import IngestUrlSerializer, WebSearchSerializer


class WebSearchView(APIView):
    """POST /api/v1/search/web/ — query the self-hosted SearXNG instance."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = WebSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        client = SearXNGClient()
        t0 = time.perf_counter()
        try:
            results = client.search(
                query=data["q"],
                count=data.get("count", 10),
                categories=data.get("categories"),
                language=data.get("language", "en"),
                time_range=data.get("time_range") or None,
            )
        except SearXNGError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        duration_ms = int((time.perf_counter() - t0) * 1000)

        record_search(
            user=request.user,
            kind="web",
            query=data["q"],
            result_count=len(results),
            duration_ms=duration_ms,
        )

        return Response({"query": data["q"], "count": len(results), "results": results})


class IngestUrlView(APIView):
    """POST /api/v1/search/ingest/url/ — create a Document and queue process_url."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = IngestUrlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        url = data["url"]
        title = (data.get("title") or url)[:512]

        doc = Document.objects.create(
            owner=request.user,
            title=title,
            source_type=Document.SOURCE_WEB,
            source_uri=url[:2048],
            status=Document.STATUS_PENDING,
            metadata=data.get("metadata") or {},
        )

        # Lazy import to avoid Celery cold-start cost at module load
        from apps.vector.tasks import process_url
        process_url.delay(doc.id)

        doc.chunk_count = 0
        return Response(
            DocumentDetailSerializer(doc, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )
