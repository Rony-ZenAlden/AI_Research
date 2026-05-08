"""Recursive text chunker.

Splits text on the most natural separators that still keep each chunk under
``chunk_size`` characters. Falls back through paragraph → newline → sentence →
clause → word → character. The result is chunks that respect semantic
boundaries instead of slicing mid-sentence like a fixed sliding window does.

Public API matches the old chunker so callers don't need to change:
    chunk_text(text, chunk_size=..., overlap=...) -> list[str]
"""
from __future__ import annotations

from typing import Iterable

# Order matters: try the highest-priority separator first; only fall through
# if the resulting parts are still bigger than ``chunk_size``.
DEFAULT_SEPARATORS: tuple[str, ...] = (
    "\n\n",   # paragraph
    "\n",     # line
    ". ",     # sentence-ish
    "! ",
    "? ",
    "; ",
    ", ",
    " ",      # word
    "",       # character (last resort)
)

DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    separators: tuple[str, ...] | None = None,
) -> list[str]:
    """Split ``text`` into semantically-bounded chunks at most ``chunk_size`` chars.

    Adds ``overlap`` characters of trailing context from the previous chunk to
    the start of each subsequent chunk so retrieval doesn't lose context at
    boundaries.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    seps = separators or DEFAULT_SEPARATORS
    raw = _recursive_split(text, list(seps), chunk_size)
    raw = [c for c in raw if c.strip()]
    return _apply_overlap(raw, overlap)


def join_iter(parts: Iterable[str], sep: str = "\n\n") -> str:
    """Helper for joining heterogeneous text blocks before chunking."""
    return sep.join(p.strip() for p in parts if p and p.strip())


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------
def _recursive_split(text: str, seps: list[str], chunk_size: int) -> list[str]:
    """Split ``text`` so every returned piece is <= ``chunk_size`` characters."""
    if len(text) <= chunk_size:
        return [text]
    if not seps:
        return _hard_split(text, chunk_size)

    sep = seps[0]
    rest = seps[1:]

    if sep == "":
        return _hard_split(text, chunk_size)

    parts = text.split(sep)
    chunks: list[str] = []
    buf = ""

    for p in parts:
        if not p:
            continue
        candidate = (buf + sep + p) if buf else p
        if len(candidate) <= chunk_size:
            buf = candidate
            continue

        # candidate too big → flush buf, then handle p separately
        if buf:
            chunks.append(buf)
            buf = ""
        if len(p) > chunk_size:
            chunks.extend(_recursive_split(p, rest, chunk_size))
        else:
            buf = p

    if buf:
        chunks.append(buf)
    return chunks


def _hard_split(text: str, chunk_size: int) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    out = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        tail = prev[-overlap:] if len(prev) > overlap else prev
        out.append(f"{tail.strip()} {chunks[i].strip()}".strip())
    return out
