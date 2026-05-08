"""Thin client for the self-hosted SearXNG instance.

We talk to SearXNG over its JSON API. The container is reachable at
``http://searxng:8080`` from inside the Docker network — see settings.SEARXNG_BASE_URL.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class SearXNGError(RuntimeError):
    pass


class SearXNGClient:
    """One client per request is fine — httpx.Client connection-pools internally."""

    def __init__(self, base_url: str | None = None, timeout: float = 12.0):
        self.base_url = (base_url or settings.SEARXNG_BASE_URL).rstrip("/")
        self.timeout = timeout

    def search(
        self,
        query: str,
        *,
        count: int = 10,
        categories: Sequence[str] | None = None,
        language: str = "en",
        time_range: str | None = None,
        safesearch: int = 1,
    ) -> list[dict[str, Any]]:
        """Run a SearXNG query and return at most ``count`` normalized results."""
        params: dict[str, str] = {
            "q": query,
            "format": "json",
            "language": language,
            "safesearch": str(safesearch),
        }
        if categories:
            params["categories"] = ",".join(categories)
        if time_range:
            params["time_range"] = time_range

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/search", data=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise SearXNGError(f"SearXNG request failed: {e}") from e
        except ValueError as e:
            raise SearXNGError(f"SearXNG returned non-JSON: {e}") from e

        results = data.get("results", []) or []
        return [self._normalize(r) for r in results[: max(1, count)]]

    @staticmethod
    def _normalize(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": (r.get("title") or "").strip(),
            "url": r.get("url") or "",
            "snippet": ((r.get("content") or "").strip())[:500],
            "engine": r.get("engine") or "",
            "score": float(r.get("score") or 0.0),
            "published_date": r.get("publishedDate") or None,
        }
