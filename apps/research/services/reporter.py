"""LLM call that turns retrieved chunks into a structured research report."""
from __future__ import annotations

import logging
from typing import Sequence

from django.conf import settings

from apps.ai.prompts import format_sources
from apps.ai.providers import get_default_provider

from ..prompts import REPORTER_SYSTEM, REPORTER_USER

logger = logging.getLogger(__name__)

MAX_SOURCES = 12
MAX_CHARS_PER_SOURCE = 1400


def synthesize_report(question: str, sources: Sequence[dict]) -> str:
    """Run the reporter LLM call. Returns markdown text."""
    if not sources:
        return "## Summary\n\n(no sources were retrieved for this question)\n"

    numbered = []
    for i, s in enumerate(sources[:MAX_SOURCES], start=1):
        numbered.append({
            "index": i,
            "title": s.get("title") or "(untitled)",
            "ref": s.get("ref") or "",
            "text": s.get("text") or "",
        })

    provider = get_default_provider()
    user_prompt = REPORTER_USER.format(
        question=question,
        sources=format_sources(numbered, max_chars_per_source=MAX_CHARS_PER_SOURCE),
    )
    text = provider.complete(
        system=REPORTER_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=int(settings.LLM_MAX_TOKENS * 1.6),
        temperature=0.2,
    )
    return text.strip()
