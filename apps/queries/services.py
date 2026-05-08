"""Tiny helper used by Semantic + Web search views to record what the user
searched. Written defensively — recording must never break the search itself.
"""
from __future__ import annotations

import logging
from typing import Any

from .models import SearchQuery

logger = logging.getLogger(__name__)


def record_search(
    *,
    user,
    kind: str,
    query: str,
    result_count: int = 0,
    duration_ms: int = 0,
    metadata: dict[str, Any] | None = None,
) -> SearchQuery | None:
    """Persist a SearchQuery row. Returns the new instance, or None if skipped/failed."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    cleaned = (query or "").strip()
    if not cleaned:
        return None
    try:
        return SearchQuery.objects.create(
            user=user,
            kind=kind,
            query=cleaned[:512],
            result_count=int(result_count or 0),
            duration_ms=int(duration_ms or 0),
            metadata=metadata or {},
        )
    except Exception:  # pragma: no cover — never fail the search itself
        logger.exception("record_search failed for user=%s kind=%s", getattr(user, "id", None), kind)
        return None
