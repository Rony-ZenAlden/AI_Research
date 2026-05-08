"""Celery tasks for asynchronous document processing.

Two tasks share the same shape:
    pending → processing → (extracted → chunked → embedded) → ready

``process_document`` extracts from an uploaded file (PDF/DOCX/TXT/MD/CSV).
``process_url`` fetches and scrapes a public web page.

Both publish progress events to Redis so the Go realtime hub can stream them
to the user's WebSocket connection in real time.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.realtime.publisher import publish_to_user

from .models import Chunk, Document
from .services import (
    ExtractionError,
    UnsupportedFileType,
    chunk_text,
    embedding_service,
    extract_text,
)

logger = logging.getLogger(__name__)


def _emit(user_id: int, doc_id: int, suffix: str, **extra) -> None:
    publish_to_user(
        user_id=user_id,
        event_type=f"document.processing.{suffix}",
        data={"document_id": doc_id, **extra},
    )


def _finalize_with_text(doc: Document, text: str, source_meta: dict, user_id: int) -> dict:
    """Shared tail of both tasks: persist text → chunk → embed → save chunks.

    Caller must already have set status=PROCESSING and emitted ``started``,
    plus already emitted ``extracted`` for ``text``.
    """
    if not text.strip():
        raise ExtractionError("no text content extracted")

    merged_meta = dict(doc.metadata or {})
    merged_meta["extraction"] = source_meta
    doc.raw_text = text
    doc.metadata = merged_meta
    doc.save(update_fields=["raw_text", "metadata", "updated_at"])

    pieces = chunk_text(text)
    _emit(user_id, doc.id, "chunked", chunk_count=len(pieces))
    if not pieces:
        raise ExtractionError("no chunks produced from extracted text")

    vectors = embedding_service.embed(pieces)
    _emit(user_id, doc.id, "embedded", chunk_count=len(pieces))

    Chunk.objects.filter(document=doc).delete()
    Chunk.objects.bulk_create(
        [
            Chunk(
                document=doc,
                position=i,
                text=piece,
                char_count=len(piece),
                embedding=vector,
            )
            for i, (piece, vector) in enumerate(zip(pieces, vectors))
        ]
    )

    doc.status = Document.STATUS_READY
    doc.processed_at = timezone.now()
    doc.save(update_fields=["status", "processed_at", "updated_at"])
    _emit(user_id, doc.id, "completed", chunk_count=len(pieces))
    return {"status": "ok", "chunks": len(pieces)}


def _mark_failed(doc: Document, user_id: int, msg: str) -> None:
    doc.status = Document.STATUS_FAILED
    doc.error_message = msg[:1000]
    doc.save(update_fields=["status", "error_message", "updated_at"])
    _emit(user_id, doc.id, "failed", error=msg)


@shared_task(bind=True, name="vector.process_document")
def process_document(self, document_id: int) -> dict:
    """Extract from uploaded file → chunk → embed → store."""
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("process_document: document_id=%s not found", document_id)
        return {"status": "missing"}
    user_id = doc.owner_id

    try:
        doc.status = Document.STATUS_PROCESSING
        doc.error_message = ""
        doc.save(update_fields=["status", "error_message", "updated_at"])
        _emit(user_id, doc.id, "started", title=doc.title, source_type=doc.source_type)

        if not doc.file:
            raise ExtractionError("document has no attached file")

        text, extraction_meta = extract_text(doc.file.path)
        _emit(user_id, doc.id, "extracted", char_count=len(text), meta=extraction_meta)

        return _finalize_with_text(doc, text, extraction_meta, user_id)

    except (UnsupportedFileType, ExtractionError) as e:
        msg = str(e)
        logger.warning("doc=%s file extraction failed: %s", document_id, msg)
        _mark_failed(doc, user_id, msg)
        return {"status": "failed", "error": msg}

    except Exception as e:
        msg = f"unexpected: {e}"
        logger.exception("doc=%s unexpected error during file processing", document_id)
        _mark_failed(doc, user_id, msg)
        raise


@shared_task(bind=True, name="vector.process_url")
def process_url(self, document_id: int) -> dict:
    """Fetch URL → extract main text → chunk → embed → store."""
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("process_url: document_id=%s not found", document_id)
        return {"status": "missing"}
    user_id = doc.owner_id
    url = doc.source_uri

    try:
        doc.status = Document.STATUS_PROCESSING
        doc.error_message = ""
        doc.save(update_fields=["status", "error_message", "updated_at"])
        _emit(user_id, doc.id, "started", title=doc.title, url=url, source_type=doc.source_type)

        # Lazy import — keeps Django/Celery startup time tight
        from apps.search.scrapers import FetchError, ScrapeError, UnsafeURLError, scrape_url

        try:
            text, extract_meta = scrape_url(url)
        except (FetchError, ScrapeError) as e:
            # Prefer the user-friendly message if the scraper provides one.
            raise ExtractionError(getattr(e, "friendly", str(e))) from e
        except UnsafeURLError as e:
            raise ExtractionError(str(e)) from e

        # Upgrade the document title from page metadata if it's still the URL
        scraped_title = (extract_meta.get("title") or "").strip()
        if scraped_title and (not doc.title.strip() or doc.title == url):
            doc.title = scraped_title[:512]
            doc.save(update_fields=["title", "updated_at"])

        _emit(user_id, doc.id, "extracted", char_count=len(text), meta=extract_meta)

        return _finalize_with_text(doc, text, extract_meta, user_id)

    except (UnsupportedFileType, ExtractionError) as e:
        msg = str(e)
        logger.warning("doc=%s url processing failed: %s", document_id, msg)
        _mark_failed(doc, user_id, msg)
        return {"status": "failed", "error": msg}

    except Exception as e:
        msg = f"unexpected: {e}"
        logger.exception("doc=%s unexpected error during url processing", document_id)
        _mark_failed(doc, user_id, msg)
        raise
