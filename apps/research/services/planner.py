"""Turn a research question into a list of web search query variants."""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable

from apps.ai.providers import get_default_provider

from ..prompts import PLANNER_SYSTEM, PLANNER_USER

logger = logging.getLogger(__name__)


def plan_search_queries(question: str, *, max_queries: int = 4) -> list[str]:
    """Ask the LLM for 3-4 search query variants. Falls back to template-based
    queries if the LLM output is unparseable, so the orchestrator always has
    something to work with.
    """
    question = (question or "").strip()
    if not question:
        return []

    provider = get_default_provider()
    try:
        raw = provider.complete(
            system=PLANNER_SYSTEM,
            messages=[{"role": "user", "content": PLANNER_USER.format(question=question)}],
            max_tokens=300,
            temperature=0.3,
        )
    except Exception as e:
        logger.warning("planner LLM call failed (%s); falling back to template", e)
        return _fallback_queries(question, max_queries)

    queries = _extract_json_array(raw)
    queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
    queries = _dedupe(queries)[:max_queries]
    if not queries:
        logger.warning("planner returned no usable queries; falling back to template")
        return _fallback_queries(question, max_queries)
    return queries


def _extract_json_array(text: str) -> list:
    """Best-effort JSON-array extraction from LLM output."""
    text = (text or "").strip()
    # 1) raw JSON
    try:
        v = json.loads(text)
        if isinstance(v, list):
            return v
    except (json.JSONDecodeError, ValueError):
        pass
    # 2) JSON inside ```json fences
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]+?\])\s*```", text)
    if fence:
        try:
            v = json.loads(fence.group(1))
            if isinstance(v, list):
                return v
        except (json.JSONDecodeError, ValueError):
            pass
    # 3) any [...] block in the text
    arr = re.search(r"\[\s*\".*?\"\s*(?:,\s*\".*?\"\s*)*\]", text, re.DOTALL)
    if arr:
        try:
            v = json.loads(arr.group(0))
            if isinstance(v, list):
                return v
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _fallback_queries(question: str, n: int) -> list[str]:
    """Cheap template fallback when the LLM doesn't cooperate."""
    q = question.rstrip("?.! ")
    candidates = [q, f"{q} overview", f"{q} comparison", f"{q} 2025"]
    return _dedupe(candidates)[:n]


def _dedupe(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for s in items:
        k = s.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(s.strip())
    return out
