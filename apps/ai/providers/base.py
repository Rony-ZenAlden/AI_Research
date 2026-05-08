"""Pluggable LLM provider interface.

All concrete drivers (Ollama today, Groq/OpenAI/Anthropic later) implement
this protocol. Callers depend only on this module — never on a specific driver.

Errors are typed so views can map them to HTTP status codes:
    LLMNotConfiguredError → 503  (no API key / no model / etc.)
    LLMAuthError          → 503
    LLMRateLimitError     → 429
    LLMProviderError      → 502  (network, 5xx, parse errors)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Literal, Sequence, TypedDict


class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """Base class for all LLM provider errors."""


class LLMNotConfiguredError(LLMError):
    """The provider is selected but missing required config (e.g. base URL, model)."""


class LLMAuthError(LLMError):
    """Authentication failed — bad/missing API key or signin needed."""


class LLMRateLimitError(LLMError):
    """Provider returned 429 / quota exceeded."""


class LLMProviderError(LLMError):
    """Anything else — network failure, 5xx, malformed response."""


class LLMProvider(ABC):
    """Common interface every driver implements."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        """Synchronous, returns the full text response."""

    @abstractmethod
    def stream(
        self,
        *,
        system: str,
        messages: Sequence[LLMMessage],
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        """Yield text deltas token-by-token."""
