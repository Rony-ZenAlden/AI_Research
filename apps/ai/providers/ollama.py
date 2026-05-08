"""Ollama driver — works with both local and Ollama Cloud (`*-cloud`) models.

Same daemon, same API endpoint (``/api/chat``); the cloud routing happens
inside the Ollama daemon based on the model name suffix. So this single class
covers every Ollama deployment: ``qwen2.5:1.5b`` (local) and
``gpt-oss:120b-cloud`` (Ollama's hosted servers) both go through this driver
unchanged.

For cloud models, the user must run ``ollama signin`` once inside the
container (auth persists in the ``ollama_data`` volume).
"""
from __future__ import annotations

import json
import logging
from typing import Iterator, Sequence

import httpx
from django.conf import settings

from .base import (
    LLMAuthError,
    LLMMessage,
    LLMNotConfiguredError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
)

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._model = model or settings.OLLAMA_MODEL
        self._timeout = timeout or settings.LLM_TIMEOUT_SECONDS
        if not self._base_url:
            raise LLMNotConfiguredError("OLLAMA_BASE_URL is not set")
        if not self._model:
            raise LLMNotConfiguredError("OLLAMA_MODEL is not set")

    # ------- metadata -------
    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        # Distinguish local vs cloud at observability time without changing routing.
        return "ollama_cloud" if self._model.endswith("-cloud") else "ollama"

    # ------- core -------
    def _build_payload(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int,
        temperature: float,
        stream: bool,
    ) -> dict:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(dict(m) for m in messages)
        return {
            "model": self._model,
            "messages": msgs,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

    def complete(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        payload = self._build_payload(
            system=system, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
            stream=False,
        )
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(f"{self._base_url}/api/chat", json=payload)
                self._check_status(resp)
                data = resp.json()
        except httpx.HTTPError as e:
            raise LLMProviderError(f"Ollama request failed: {e}") from e
        except ValueError as e:  # JSON decode
            raise LLMProviderError(f"Ollama returned non-JSON: {e}") from e

        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as e:
            raise LLMProviderError(f"unexpected Ollama response shape: {data}") from e

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        payload = self._build_payload(
            system=system, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
            stream=True,
        )
        try:
            with httpx.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            ) as resp:
                self._check_status(resp)
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = chunk.get("message") or {}
                    delta = msg.get("content")
                    if delta:
                        yield delta
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as e:
            raise LLMProviderError(f"Ollama stream failed: {e}") from e

    # ------- internals -------
    def _check_status(self, resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        body = ""
        try:
            body = resp.text[:300]
        except Exception:
            pass
        if resp.status_code == 401 or resp.status_code == 403:
            raise LLMAuthError(
                f"Ollama auth failed ({resp.status_code}). "
                "For *-cloud models run `docker compose exec ollama ollama signin` once."
            )
        if resp.status_code == 404:
            raise LLMNotConfiguredError(
                f"Ollama returned 404 for model '{self._model}'. "
                f"For local models run `docker compose exec ollama ollama pull {self._model}`."
            )
        if resp.status_code == 429:
            raise LLMRateLimitError("Ollama Cloud rate limit reached. Try again shortly.")
        raise LLMProviderError(f"Ollama HTTP {resp.status_code}: {body}")
