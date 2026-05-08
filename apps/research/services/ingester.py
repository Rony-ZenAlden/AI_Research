"""Inline web ingestion: scrape → chunk → embed → save Documents.

Lives separately from apps.vector.tasks.process_url because the research
orchestrator runs *inside* a Celery task — we don't want to spawn sub-tasks
and wait. Doing it inline is simpler, faster, and easier to track progress
through the parent task's emitter.
"""
from __future__ import annotations

import logging
from typing import Callable

from django.utils import timezone

from apps.search.scrapers import FetchError, ScrapeError, UnsafeURLError, scrape_url
from apps.vector.models import Chunk, Document
from apps.vector.services import chunk_text, embedding_service

logger = logging.getLogger(__name__)


def ingest_search_result(
    *,
    user,
    url: str,
    fallback_title: str = "",
    metadata: dict | None = None,
) -> tuple[int | None, str]:
    """Fetch + extract + chunk + embed + persist a Document.

    Returns ``(document_id, status_message)``. ``document_id`` is None when the
    page failed (status_message describes why).
    """
    metadata = dict(metadata or {})
    try:
        text, scrape_meta = scrape_url(url)
    except (FetchError, ScrapeError) as e:
        return None, getattr(e, "friendly", str(e))
    except UnsafeURLError as e:
        return None, str(e)
    except Exception as e:
        logger.exception("scrape_url unexpected error for %s", url)
        return None, f"unexpected: {e}"

    if not text or len(text.strip()) < 200:
        return None, "page has too little extractable text"

    title = (scrape_meta.get("title") or fallback_title or url)[:512]

    pieces = chunk_text(text)
    if not pieces:
        return None, "no chunks produced"
    vectors = embedding_service.embed_documents(pieces)

    doc = Document.objects.create(
        owner=user,
        title=title,
        source_type=Document.SOURCE_WEB,
        source_uri=url[:2048],
        raw_text=text,
        status=Document.STATUS_READY,
        metadata={**metadata, "extraction": scrape_meta},
        processed_at=timezone.now(),
    )
    Chunk.objects.bulk_create(
        [
            Chunk(
                document=doc,
                position=i,
                text=p,
                char_count=len(p),
                embedding=v,
            )
            for i, (p, v) in enumerate(zip(pieces, vectors))
        ]
    )
    return doc.id, f"{len(pieces)} chunks"


def ingest_many(
    *,
    user,
    results: list[dict],
    on_progress: Callable[[str, dict], None] | None = None,
) -> list[int]:
    """Iterate a list of SearXNG-shaped results, ingest each. Calls on_progress
    with status updates: ``on_progress("ok"|"skip", {url, title, message, document_id?})``.
    Returns list of created document IDs (in order of success).
    """
    created: list[int] = []
    for r in results:
        url = r.get("url") or ""
        title_hint = r.get("title") or ""
        if not url:
            continue
        doc_id, msg = ingest_search_result(
            user=user, url=url, fallback_title=title_hint,
        )
        if doc_id:
            created.append(doc_id)
            if on_progress:
                on_progress("ok", {"url": url, "title": title_hint, "message": msg, "document_id": doc_id})
        else:
            if on_progress:
                on_progress("skip", {"url": url, "title": title_hint, "message": msg})
    return created
