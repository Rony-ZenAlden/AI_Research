"""Orchestrates a single LLM call: query + sources → grounded text response."""
from __future__ import annotations

import logging
import time
from typing import Any

from django.conf import settings

from ..prompts import (
    COMPARE_SYSTEM,
    COMPARE_USER,
    SUMMARIZE_SYSTEM,
    SUMMARIZE_USER,
    format_sources,
)
from ..providers import get_default_provider

logger = logging.getLogger(__name__)

MAX_SOURCES = 10
MAX_CHARS_PER_SOURCE = 1500


def synthesize(*, query: str, mode: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Run a single LLM call and return a structured response.

    Args:
        query: the user's question.
        mode: "summarize" or "compare".
        sources: list of dicts; each must have ``title`` + ``text``; ``ref`` optional.
                 We re-number them positionally so [1] is always the first source.

    Returns:
        ``{"text", "mode", "model", "provider", "duration_ms", "sources"}``
    """
    if mode not in ("summarize", "compare"):
        raise ValueError(f"unknown mode: {mode}")

    # Number sources positionally so [N] in the output is unambiguous.
    numbered = []
    for i, s in enumerate(sources[:MAX_SOURCES], start=1):
        numbered.append({
            "index": i,
            "title": s.get("title") or "(untitled)",
            "ref": s.get("ref") or "",
            "text": s.get("text") or "",
        })

    if not numbered:
        return {
            "mode": mode,
            "text": "No sources were provided to synthesize.",
            "model": "",
            "provider": "",
            "duration_ms": 0,
            "sources": [],
        }

    if mode == "compare":
        sys_prompt = COMPARE_SYSTEM
        user_prompt = COMPARE_USER.format(
            query=query, sources=format_sources(numbered, MAX_CHARS_PER_SOURCE)
        )
    else:
        sys_prompt = SUMMARIZE_SYSTEM
        user_prompt = SUMMARIZE_USER.format(
            query=query, sources=format_sources(numbered, MAX_CHARS_PER_SOURCE)
        )

    provider = get_default_provider()
    max_tokens = settings.LLM_MAX_TOKENS

    t0 = time.perf_counter()
    text = provider.complete(
        system=sys_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=max_tokens if mode == "summarize" else int(max_tokens * 1.4),
        temperature=0.2,
    )
    dt = int((time.perf_counter() - t0) * 1000)

    return {
        "mode": mode,
        "text": text.strip(),
        "model": provider.model_name,
        "provider": provider.provider_name,
        "duration_ms": dt,
        "sources": [
            {"index": s["index"], "title": s["title"], "ref": s["ref"]}
            for s in numbered
        ],
    }
