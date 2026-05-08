"""Multi-step research orchestrator.

Stages: pending → planning → searching → fetching → retrieving → synthesizing → ready
                                                                                ↓
                                                                              failed

Every transition publishes a ``research.progress`` event over Redis pub/sub
so the Go realtime hub can stream it to the user's open WebSocket connection.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from celery import shared_task
from django.utils import timezone

from apps.realtime.publisher import publish_to_user
from apps.search.searxng import SearXNGClient, SearXNGError
from apps.vector.models import Chunk
from apps.vector.services import hybrid_search

from .models import ResearchSession
from .services.ingester import ingest_many
from .services.planner import plan_search_queries
from .services.reporter import synthesize_report

logger = logging.getLogger(__name__)


# Per-search-variant URL count, and overall fetch cap.
URLS_PER_QUERY = 5
MAX_PAGES_TO_FETCH = 6
RETRIEVE_TOP_K = 12


class OrchestratorError(RuntimeError):
    pass


def _emit(session: ResearchSession, step: str, **extra: Any) -> None:
    publish_to_user(
        user_id=session.user_id,
        event_type="research.progress",
        data={"session_id": session.id, "step": step, **extra},
    )


def _emit_terminal(session: ResearchSession, type_: str, **extra: Any) -> None:
    publish_to_user(
        user_id=session.user_id,
        event_type=f"research.{type_}",
        data={"session_id": session.id, **extra},
    )


def _set_status(session: ResearchSession, status: str) -> None:
    session.status = status
    session.save(update_fields=["status", "updated_at"])


@shared_task(bind=True, name="research.run_session")
def run_research_session(self, session_id: int) -> dict:
    """Orchestrate one research session end-to-end."""
    try:
        session = ResearchSession.objects.get(pk=session_id)
    except ResearchSession.DoesNotExist:
        logger.error("run_research_session: session %s not found", session_id)
        return {"status": "missing"}

    t0 = time.perf_counter()
    user = session.user

    try:
        # ===== 1. Plan =====
        _set_status(session, ResearchSession.STATUS_PLANNING)
        _emit(session, "planning", message="Drafting search queries…")
        queries = plan_search_queries(session.question)
        if not queries:
            raise OrchestratorError("Could not plan any search queries")
        session.plan = {"queries": queries}
        session.save(update_fields=["plan", "updated_at"])
        _emit(session, "planned", queries=queries, message=f"Generated {len(queries)} search variant(s)")

        # ===== 2. Search the web =====
        _set_status(session, ResearchSession.STATUS_SEARCHING)
        _emit(session, "searching", message=f"Querying SearXNG ({len(queries)} variants)…")
        client = SearXNGClient()
        all_results: list[dict] = []
        for q in queries:
            try:
                hits = client.search(q, count=URLS_PER_QUERY)
                all_results.extend(hits)
            except SearXNGError as e:
                logger.warning("SearXNG query '%s' failed: %s", q, e)

        # Dedupe by URL, preserve order
        seen, deduped = set(), []
        for r in all_results:
            url = r.get("url") or ""
            if url and url not in seen:
                seen.add(url)
                deduped.append(r)
        deduped = deduped[:MAX_PAGES_TO_FETCH]
        if not deduped:
            raise OrchestratorError("No web results found for any of the planned queries")
        _emit(session, "searched",
              found=len(all_results), unique=len(deduped),
              urls=[r.get("url", "") for r in deduped],
              message=f"Picked {len(deduped)} unique pages to ingest")

        # ===== 3. Fetch + ingest =====
        _set_status(session, ResearchSession.STATUS_FETCHING)
        _emit(session, "fetching", message=f"Fetching {len(deduped)} pages…")

        def _on_ingest_progress(kind: str, info: dict) -> None:
            _emit(session, "fetching",
                  url=info.get("url", ""),
                  title=info.get("title", ""),
                  outcome=kind,
                  message=info.get("message", ""))

        doc_ids = ingest_many(
            user=user,
            results=deduped,
            on_progress=_on_ingest_progress,
        )
        if not doc_ids:
            raise OrchestratorError(
                "Could not ingest any of the fetched URLs (all failed extraction)."
            )
        session.document_ids = doc_ids
        session.save(update_fields=["document_ids", "updated_at"])
        _emit(session, "fetched",
              ingested=len(doc_ids), attempted=len(deduped),
              message=f"Ingested {len(doc_ids)} of {len(deduped)} pages")

        # ===== 4. Retrieve (hybrid: vector + keyword, RRF-fused) =====
        _set_status(session, ResearchSession.STATUS_RETRIEVING)
        _emit(session, "retrieving", message="Selecting most relevant passages (hybrid retrieval)…")

        # Restrict the universe to docs we just ingested for THIS session by
        # owner-scoping then filtering. We use a small wrapper rather than
        # call hybrid_search directly because that function searches the
        # whole user library; here we want only the new docs.
        from apps.vector.services.retrieval import hybrid_search as _hs  # noqa: F401
        # Use full user-scoped hybrid search but post-filter to this session's docs.
        all_hits = _hs(user=user, query=session.question, top_k=RETRIEVE_TOP_K * 3, mode="hybrid")
        doc_id_set = set(doc_ids)
        hits = [h for h in all_hits if h.chunk.document_id in doc_id_set][:RETRIEVE_TOP_K]
        if not hits:
            raise OrchestratorError("No chunks were available after ingestion")
        _emit(session, "retrieved",
              picked=len(hits),
              message=f"Selected top {len(hits)} passages from {len(doc_ids)} pages")

        # Build citation map
        sources = []
        for i, h in enumerate(hits, start=1):
            sources.append({
                "index": i,
                "title": h.chunk.document.title,
                "ref": h.chunk.document.source_uri or f"document {h.chunk.document_id}",
                "text": h.chunk.text,
            })

        # ===== 5. Synthesize =====
        _set_status(session, ResearchSession.STATUS_SYNTHESIZING)
        _emit(session, "synthesizing", message="Writing the report (this may take a moment)…")
        report = synthesize_report(session.question, sources)

        # ===== 6. Save =====
        session.report_text = report
        session.report_sources = [
            {"index": s["index"], "title": s["title"], "ref": s["ref"]}
            for s in sources
        ]
        session.status = ResearchSession.STATUS_READY
        session.completed_at = timezone.now()
        session.duration_ms = int((time.perf_counter() - t0) * 1000)
        session.save()
        _emit_terminal(session, "completed",
                       chunk_count=len(chunks),
                       duration_ms=session.duration_ms,
                       message="Report ready")
        return {"status": "ok", "session_id": session.id, "chunks": len(chunks)}

    except OrchestratorError as e:
        msg = str(e)
        logger.warning("research session %s failed: %s", session_id, msg)
        session.status = ResearchSession.STATUS_FAILED
        session.error_message = msg[:1000]
        session.save(update_fields=["status", "error_message", "updated_at"])
        _emit_terminal(session, "failed", error=msg)
        return {"status": "failed", "error": msg}

    except Exception as e:
        msg = f"unexpected: {e}"
        logger.exception("research session %s crashed", session_id)
        session.status = ResearchSession.STATUS_FAILED
        session.error_message = msg[:1000]
        session.save(update_fields=["status", "error_message", "updated_at"])
        _emit_terminal(session, "failed", error=str(e))
        raise
