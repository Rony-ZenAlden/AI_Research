"""Singleton embedding service.

Default model: ``BAAI/bge-small-en-v1.5`` — 384-dim (drop-in for the prior
all-MiniLM-L6-v2), measurably better retrieval on MTEB. Same memory footprint
class.

BGE recommends a query-side instruction prefix for asymmetric retrieval, so we
expose two methods:

    embed_documents(passages) -> list[list[float]]   # no prefix
    embed_query(text)         -> list[float]         # prefix added internally

Old aliases ``embed`` / ``embed_one`` are kept for backwards-compat — they
behave like passage embedding (no prefix).
"""
from __future__ import annotations

import logging
import threading
from functools import cached_property
from typing import Sequence

from django.conf import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Thread-safe lazy-loading wrapper around sentence-transformers."""

    # Per the BGE model card — boost retrieval precision for query embeddings.
    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    _instance: "EmbeddingService | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "EmbeddingService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_load_lock"):
            self._load_lock = threading.Lock()
            self._model = None  # type: ignore[assignment]

    @cached_property
    def dimension(self) -> int:
        return int(settings.EMBEDDING_DIM)

    @cached_property
    def model_name(self) -> str:
        return settings.EMBEDDING_MODEL_NAME

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name, device="cpu")
            logger.info("Embedding model ready (dim=%d)", self.dimension)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        embeddings = self._model.encode(  # type: ignore[union-attr]
            texts,
            batch_size=16,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    # ---- new explicit-asymmetric API ----------------------------------------
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(list(texts))

    def embed_query(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.dimension
        return self._encode([self.QUERY_INSTRUCTION + text])[0]

    # ---- legacy aliases (treated as passage embedding) ----------------------
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    def embed_one(self, text: str) -> list[float]:
        return self.embed_documents([text])[0] if text else [0.0] * self.dimension


embedding_service = EmbeddingService()
