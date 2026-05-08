"""Ingestion orchestrator: text → chunks → embeddings → DB rows."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

from ..models import Chunk, Document
from .chunker import chunk_text
from .embedder import embedding_service

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()

logger = logging.getLogger(__name__)


@transaction.atomic
def ingest_text(
    *,
    owner,
    title: str,
    text: str,
    source_type: str = Document.SOURCE_TEXT,
    source_uri: str = "",
    metadata: dict[str, Any] | None = None,
    chunk_size: int = 500,
    overlap: int = 50,
) -> Document:
    """Create a Document and embed its chunks in a single transaction.

    All work happens inline for now — Phase 1 step 2 keeps things simple.
    We move this to a Celery task in Phase 1 step 4 once file uploads land.
    """
    metadata = metadata or {}

    document = Document.objects.create(
        owner=owner,
        title=title,
        source_type=source_type,
        source_uri=source_uri,
        raw_text=text,
        metadata=metadata,
    )

    pieces = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not pieces:
        logger.warning("ingest_text produced 0 chunks for document=%s", document.pk)
        return document

    vectors = embedding_service.embed(pieces)

    Chunk.objects.bulk_create(
        [
            Chunk(
                document=document,
                position=i,
                text=piece,
                char_count=len(piece),
                embedding=vector,
            )
            for i, (piece, vector) in enumerate(zip(pieces, vectors))
        ]
    )
    logger.info("Ingested %d chunks for document=%s", len(pieces), document.pk)
    return document
