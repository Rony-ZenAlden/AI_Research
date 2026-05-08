"""Prompt templates for the AI surface.

Two modes share the same source-block format; only the system prompt and
output instructions change. Keeping them as constants makes them easy to
tweak and review.
"""
from __future__ import annotations


SUMMARIZE_SYSTEM = """You are a precise research assistant. Given a query and numbered source excerpts, write a concise summary that answers the query.

Strict rules:
- Cite EVERY factual claim with [N] referring to the numbered source below.
- Use multiple citations like [1][3] when several sources support a claim.
- If the sources don't address part of the query, say so explicitly.
- Be concise: 3 to 6 sentences for short queries, slightly longer only when warranted.
- Output plain prose. No markdown headers, no bullet lists.
- Never invent facts. Stay grounded in the sources."""


SUMMARIZE_USER = """Query: {query}

Sources:
{sources}

Write the summary now. Remember to cite EVERY claim with [N]."""


COMPARE_SYSTEM = """You are a precise research assistant. Given a query and numbered source excerpts, compare what the sources say.

Strict rules:
- Cite EVERY claim with [N] referring to the numbered source below.
- Output exactly these three sections in this order, using markdown headers:
  ## Where sources agree
  ## Where sources differ
  ## What's not covered
- Each section uses bullet points starting with "- ".
- If a section is empty, write a single bullet "- (none)" — do not omit the section.
- Be specific. Quote brief phrases when useful.
- Never invent disagreements that aren't in the sources."""


COMPARE_USER = """Query: {query}

Sources:
{sources}

Produce the comparison now. Use the three required headers."""


def format_sources(sources: list[dict], max_chars_per_source: int = 1500) -> str:
    """Render numbered source blocks for the prompt.

    Each source is a dict with at least: ``index``, ``title``, ``text``.
    Optional: ``ref`` (a chunk locator or URL).
    """
    parts: list[str] = []
    for s in sources:
        n = s["index"]
        title = (s.get("title") or "").strip() or "(untitled)"
        ref = (s.get("ref") or "").strip()
        text = (s.get("text") or "").strip()[:max_chars_per_source]
        header = f"[{n}] {title}"
        if ref:
            header += f"  —  {ref}"
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)
