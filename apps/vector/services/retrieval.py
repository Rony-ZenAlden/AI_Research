"""Hybrid retrieval = pgvector cosine + Postgres full-text search, fused with RRF.

Why both?
  * Vector search catches semantic matches ("plants make food from light"
    → photosynthesis chunks).
  * Keyword search catches exact-string matches that semantics miss
    ("HNSW", "ef_construction", proper nouns, model names).

Reciprocal Rank Fusion (RRF) is the dead-simple, hyperparameter-free way to
merge two ranked lists: each ranked list contributes ``1 / (k + rank)`` to the
combined score. ``k=60`` is the published sweet spot from the original paper.

This module owns the retrieval algorithm; the view layer wraps it in HTTP.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Literal

from django.contrib.postgres.search import SearchQuery
from pgvector.django import CosineDistance

from ..models import Chunk
from .embedder import embedding_service

logger = logging.getLogger(__name__)

# RRF default per the paper. Stable, well-cited.
RRF_K = 60

# How many candidates each ranker contributes before fusion.
PER_RANKER_LIMIT = 30


@dataclass
class HybridHit:
    chunk: Chunk
    score: float          # cosine similarity if vector hit, else 0.0 — for display
    rrf_score: float      # the fused score that was used for ranking
    matched_by: list[str] # ["vector", "keyword"] / ["vector"] / ["keyword"]


def hybrid_search(
    *,
    user,
    query: str,
    top_k: int = 10,
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid",
) -> list[HybridHit]:
    """Return up to ``top_k`` HybridHits for ``query`` over ``user``'s chunks.

    ``mode='hybrid'`` (default) runs both rankers and fuses with RRF.
    ``mode='vector'`` and ``mode='keyword'`` skip fusion and return one source's
    ranking — handy for measurement / debugging.
    """
    query = (query or "").strip()
    if not query:
        return []

    do_vector = mode in ("hybrid", "vector")
    do_keyword = mode in ("hybrid", "keyword")

    base_qs = Chunk.objects.filter(document__owner=user)

    vector_ids: list[int] = []
    vector_distance_by_id: dict[int, float] = {}
    if do_vector:
        qvec = embedding_service.embed_query(query)
        vector_chunks = list(
            base_qs.annotate(distance=CosineDistance("embedding", qvec))
            .order_by("distance")
            .values_list("id", "distance")[:PER_RANKER_LIMIT]
        )
        vector_ids = [cid for cid, _ in vector_chunks]
        vector_distance_by_id = {cid: float(dist) for cid, dist in vector_chunks}

    keyword_ids: list[int] = []
    if do_keyword:
        # ``websearch`` parser is forgiving — handles natural-language queries
        # ("how do plants make food") rather than requiring boolean operators.
        sq = SearchQuery(query, search_type="websearch", config="english")
        keyword_chunks = list(
            base_qs.filter(search_vector=sq)
            .extra(  # noqa: SLF001 - simple ts_rank_cd, easier than a proper annotation
                select={"_kw_rank": "ts_rank_cd(search_vector, plainto_tsquery('english', %s))"},
                select_params=[query],
            )
            .order_by("-_kw_rank")
            .values_list("id", flat=True)[:PER_RANKER_LIMIT]
        )
        keyword_ids = list(keyword_chunks)

    # Single-source modes skip RRF
    if mode == "vector":
        return _materialize(vector_ids, vector_distance_by_id, set(), top_k, "vector")
    if mode == "keyword":
        return _materialize(keyword_ids, vector_distance_by_id, set(keyword_ids), top_k, "keyword")

    # Hybrid: fuse with RRF
    rrf = _reciprocal_rank_fusion([vector_ids, keyword_ids])
    if not rrf:
        return []

    sorted_ids = sorted(rrf.keys(), key=lambda i: rrf[i], reverse=True)[:top_k]
    chunks_by_id = {
        c.id: c
        for c in Chunk.objects.filter(id__in=sorted_ids).select_related("document")
    }
    vector_set = set(vector_ids)
    keyword_set = set(keyword_ids)

    out: list[HybridHit] = []
    for cid in sorted_ids:
        chunk = chunks_by_id.get(cid)
        if chunk is None:
            continue
        matched: list[str] = []
        if cid in vector_set:
            matched.append("vector")
        if cid in keyword_set:
            matched.append("keyword")
        cosine_dist = vector_distance_by_id.get(cid)
        score = 1.0 - cosine_dist if cosine_dist is not None else 0.0
        out.append(HybridHit(
            chunk=chunk,
            score=max(0.0, min(1.0, score)),
            rrf_score=float(rrf[cid]),
            matched_by=matched,
        ))
    return out


def _materialize(
    ids: list[int],
    vector_distance_by_id: dict[int, float],
    keyword_set: set[int],
    top_k: int,
    forced_match: str,
) -> list[HybridHit]:
    if not ids:
        return []
    ids = ids[:top_k]
    chunks_by_id = {
        c.id: c
        for c in Chunk.objects.filter(id__in=ids).select_related("document")
    }
    out: list[HybridHit] = []
    for rank, cid in enumerate(ids, start=1):
        chunk = chunks_by_id.get(cid)
        if chunk is None:
            continue
        cosine_dist = vector_distance_by_id.get(cid)
        score = 1.0 - cosine_dist if cosine_dist is not None else (1.0 / rank)
        matched = [forced_match]
        if forced_match == "keyword" and cid in vector_distance_by_id:
            matched.append("vector")
        out.append(HybridHit(
            chunk=chunk,
            score=max(0.0, min(1.0, score)),
            rrf_score=1.0 / rank,
            matched_by=matched,
        ))
    return out


def _reciprocal_rank_fusion(
    rankings: Iterable[Iterable[int]],
    *,
    k: int = RRF_K,
) -> dict[int, float]:
    """Sum 1/(k+rank) across all rankings for each chunk id."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores
