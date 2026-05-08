import re

from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .exporters import render_markdown, render_pdf
from .models import ResearchSession
from .serializers import (
    CreateResearchSessionSerializer,
    ResearchSessionDetailSerializer,
    ResearchSessionSummarySerializer,
)


def _safe_filename(text: str, max_len: int = 60) -> str:
    base = re.sub(r"[^A-Za-z0-9\-_]+", "-", (text or "report").strip())
    base = re.sub(r"-+", "-", base).strip("-").lower()
    return (base or "report")[:max_len]


class ResearchSessionListCreateView(APIView):
    """GET /api/v1/research/sessions/  — list caller's sessions
    POST /api/v1/research/sessions/ — create new session, dispatch orchestrator
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = ResearchSession.objects.filter(user=request.user).order_by("-created_at")[:50]
        data = ResearchSessionSummarySerializer(qs, many=True).data
        return Response({"results": data, "count": len(data)})

    def post(self, request):
        serializer = CreateResearchSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = ResearchSession.objects.create(
            user=request.user,
            question=serializer.validated_data["question"].strip(),
            status=ResearchSession.STATUS_PENDING,
        )
        # Lazy import — keeps Django startup time fast
        from .tasks import run_research_session
        run_research_session.delay(session.id)
        return Response(
            ResearchSessionDetailSerializer(session).data,
            status=status.HTTP_202_ACCEPTED,
        )


class ResearchSessionDetailView(generics.RetrieveDestroyAPIView):
    """GET / DELETE /api/v1/research/sessions/<id>/"""
    serializer_class = ResearchSessionDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ResearchSession.objects.filter(user=self.request.user)


class _BaseExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_session(self, request, pk: int) -> ResearchSession:
        try:
            session = ResearchSession.objects.get(pk=pk, user=request.user)
        except ResearchSession.DoesNotExist:
            raise NotFound("session not found")
        if session.status != ResearchSession.STATUS_READY:
            raise NotFound("session is not ready yet")
        return session


class ResearchExportMarkdownView(_BaseExportView):
    """GET /api/v1/research/sessions/<id>/export.md — download .md file."""

    def get(self, request, pk):
        session = self._get_session(request, pk)
        body = render_markdown(session)
        resp = HttpResponse(body, content_type="text/markdown; charset=utf-8")
        fname = _safe_filename(session.question)
        resp["Content-Disposition"] = f'attachment; filename="{fname}.md"'
        return resp


class ResearchExportPdfView(_BaseExportView):
    """GET /api/v1/research/sessions/<id>/export.pdf — download .pdf file."""

    def get(self, request, pk):
        session = self._get_session(request, pk)
        try:
            pdf_bytes = render_pdf(session)
        except Exception as e:
            return Response(
                {"error": f"PDF rendering failed: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        fname = _safe_filename(session.question)
        resp["Content-Disposition"] = f'attachment; filename="{fname}.pdf"'
        return resp
