"""Pick a concrete LLMProvider based on settings.LLM_PROVIDER."""
from __future__ import annotations

from django.conf import settings

from .base import LLMNotConfiguredError, LLMProvider


def get_default_provider() -> LLMProvider:
    """Return the configured provider instance. Raises LLMNotConfiguredError if missing."""
    name = (getattr(settings, "LLM_PROVIDER", "ollama") or "").lower().strip()
    if name == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider()
    raise LLMNotConfiguredError(
        f"Unknown LLM_PROVIDER='{name}'. Supported: ollama. "
        "Add a new driver in apps/ai/providers/ to extend."
    )
