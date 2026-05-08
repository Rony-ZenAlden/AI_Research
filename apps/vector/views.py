import time

from django.db.models import Count
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.queries.services import record_search

from .models import Chunk, Document
from .serializers import (
    ChunkSerializer,
    DocumentDetailSerializer,
    DocumentSummarySerializer,
    IngestFileSerializer,
    IngestTextSerializer,
    SearchHitSerializer,
)
from .services import hybrid_search, ingest_text

VALID_SEARCH_MODES = {"hybrid", "vector", "keyword"}


# Curated demo URLs — keep them small, stable, topical, and non-paywalled.
DEMO_URLS: list[dict] = [
    {
        "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
        "title": "Retrieval-augmented generation",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Vector_database",
        "title": "Vector database",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Sentence_embedding",
        "title": "Sentence embedding",
    },
]


class IngestTextView(APIView):
    """POST /api/v1/vector/ingest/text/ — synchronous text ingestion."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = IngestTextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document = ingest_text(
            owner=request.user,
            title=serializer.validated_data["title"],
            text=serializer.validated_data["text"],
            metadata=serializer.validated_data.get("metadata") or {},
        )
        document.chunk_count = document.chunks.count()
        return Response(
            DocumentSummarySerializer(document).data,
            status=status.HTTP_201_CREATED,
        )


class IngestFileView(APIView):
    """POST /api/v1/vector/ingest/file/ — accept upload, queue Celery task, return 202."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = IngestFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        title = (serializer.validated_data.get("title") or upload.name)[:512]
        metadata = serializer.validated_data.get("metadata") or {}

        doc = Document.objects.create(
            owner=request.user,
            title=title,
            source_type=Document.SOURCE_FILE,
            source_uri=upload.name[:2048],
            status=Document.STATUS_PENDING,
            file=upload,
            file_size_bytes=upload.size,
            mime_type=getattr(upload, "content_type", "") or "",
            metadata=metadata,
        )

        from .tasks import process_document
        process_document.delay(doc.id)

        doc.chunk_count = 0
        return Response(
            DocumentDetailSerializer(doc, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentListView(generics.ListAPIView):
    """GET /api/v1/vector/documents/ — list the caller's documents."""
    serializer_class = DocumentSummarySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Document.objects.filter(owner=self.request.user)
            .annotate(chunk_count=Count("chunks"))
            .order_by("-created_at")
        )


class DocumentDetailView(generics.RetrieveDestroyAPIView):
    """GET / DELETE /api/v1/vector/documents/<id>/ — inspect or delete one doc."""
    serializer_class = DocumentDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user).annotate(
            chunk_count=Count("chunks")
        )

    def perform_destroy(self, instance):
        # Remove the underlying file too — Chunks cascade via FK.
        if instance.file:
            instance.file.delete(save=False)
        instance.delete()


class DocumentChunksView(generics.ListAPIView):
    """GET /api/v1/vector/documents/<id>/chunks/ — chunks of one doc, ordered."""
    serializer_class = ChunkSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # full chunk list

    def get_queryset(self):
        return Chunk.objects.filter(
            document_id=self.kwargs["pk"],
            document__owner=self.request.user,
        ).order_by("position")


class LoadDemoDataView(APIView):
    """POST /api/v1/vector/load-demo/ — queue ingestion of curated demo URLs."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .tasks import process_url

        created_ids: list[int] = []
        for item in DEMO_URLS:
            doc = Document.objects.create(
                owner=request.user,
                title=item["title"],
                source_type=Document.SOURCE_WEB,
                source_uri=item["url"],
                status=Document.STATUS_PENDING,
                metadata={"demo": True},
            )
            process_url.delay(doc.id)
            created_ids.append(doc.id)

        return Response(
            {"queued": len(created_ids), "document_ids": created_ids},
            status=status.HTTP_202_ACCEPTED,
        )


class SemanticSearchView(APIView):
    """GET /api/v1/vector/search/?q=...&top_k=5&mode=hybrid

    ``mode``: hybrid (default) | vector | keyword
        - hybrid:  pgvector + Postgres FTS, fused with reciprocal rank fusion
        - vector:  embedding cosine only (legacy behaviour)
        - keyword: Postgres FTS only
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if not query:
            raise ValidationError({"q": "Query parameter 'q' is required."})
        try:
            top_k = int(request.query_params.get("top_k", 10))
        except (TypeError, ValueError):
            raise ValidationError({"top_k": "Must be an integer."})
        top_k = max(1, min(top_k, 50))

        mode = (request.query_params.get("mode") or "hybrid").strip().lower()
        if mode not in VALID_SEARCH_MODES:
            raise ValidationError({"mode": f"must be one of {sorted(VALID_SEARCH_MODES)}"})

        t0 = time.perf_counter()
        hits = hybrid_search(user=request.user, query=query, top_k=top_k, mode=mode)
        duration_ms = int((time.perf_counter() - t0) * 1000)

        results = [SearchHitSerializer.from_hybrid_hit(h) for h in hits]

        record_search(
            user=request.user,
            kind="semantic",
            query=query,
            result_count=len(results),
            duration_ms=duration_ms,
            metadata={"mode": mode},
        )

        return Response({"query": query, "top_k": top_k, "mode": mode, "results": results})
