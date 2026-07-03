"""Fallback model chain — automatic provider/model failover for high availability.

When the primary model call fails (API error, rate limit, context overflow,
timeout), the fallback chain tries the next configured model/provider pair.

Config (``fallback_model_chain`` in ``config.yaml``)::

    fallback_model_chain:
      - provider: openrouter
        model: deepseek/deepseek-v4-pro
      - provider: anthropic
        model: claude-opus-4.8
      - provider: openai-codex
        model: gpt-5.5

    fallback_providers:
      - openrouter
      - anthropic
      - openai-codex

Integration:
    The fallback chain is applied in ``agent/chat_completion_helpers.py`` and
    ``run_agent.py`` whenever the primary API call fails with a retryable error.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ModelEntry:
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    api_mode: str = ""


@dataclass
class FallbackResult:
    success: bool
    response: Any = None
    model_used: str = ""
    provider_used: str = ""
    error: str = ""
    attempts: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Chain executor
# ---------------------------------------------------------------------------


def _load_fallback_chain() -> list[ModelEntry]:
    """Load the fallback model chain from config."""
    try:
        from alex_cli.config import load_config

        config = load_config()
        chain = config.get("fallback_model_chain", [])
        if chain:
            return [ModelEntry(**entry) for entry in chain]

        providers = config.get("fallback_providers", [])
        model = config.get("model", "")
        if providers and model:
            return [ModelEntry(provider=p, model=model) for p in providers]
    except Exception as exc:
        logger.debug("Could not load fallback chain from config: %s", exc)

    return []


def execute_with_fallback(
    primary_call: Callable[[], Any],
    primary_model: str,
    primary_provider: str,
    *,
    fallback_chain: list[ModelEntry] | None = None,
    retryable_errors: tuple[type[Exception], ...] | None = None,
    max_retries_per_model: int = 1,
    switch_callback: Callable[[str, str], None] | None = None,
) -> FallbackResult:
    """Execute an API call with automatic fallback through a model chain.

    Args:
        primary_call: The primary model API call function.
        primary_model: The primary model name (for logging).
        primary_provider: The primary provider name (for logging).
        fallback_chain: List of fallback model/provider entries. Loaded from
            config if ``None``.
        retryable_errors: Exception types that trigger a fallback.
            Defaults to connection/rate-limit/API errors.
        max_retries_per_model: Number of retries per model before
            moving to the next fallback.
        switch_callback: Called when switching to a fallback model,
            receives (provider, model).

    Returns:
        ``FallbackResult`` with the successful response or the last error.
    """
    if retryable_errors is None:
        from httpx import (
            ConnectError, ConnectTimeout, ReadTimeout, RemoteProtocolError,
        )
        from openai import (
            APIConnectionError, APIStatusError, RateLimitError,
            InternalServerError,
        )

        retryable_errors = (
            ConnectError, ConnectTimeout, ReadTimeout, RemoteProtocolError,
            APIConnectionError, APIStatusError, RateLimitError,
            InternalServerError,
            ConnectionError, TimeoutError,
        )

    if fallback_chain is None:
        fallback_chain = _load_fallback_chain()

    attempts: list[dict[str, Any]] = []
    all_entries: list[ModelEntry] = [
        ModelEntry(provider=primary_provider, model=primary_model),
    ]
    all_entries.extend(fallback_chain)

    for entry in all_entries:
        for attempt_num in range(1, max_retries_per_model + 1):
            label = f"{entry.provider}/{entry.model}"
            logger.info(
                "Fallback attempt %d/%d for %s",
                attempt_num, max_retries_per_model, label,
            )

            if switch_callback and (entry.provider != primary_provider or entry.model != primary_model):
                try:
                    switch_callback(entry.provider, entry.model)
                except Exception:
                    pass

            try:
                start = time.monotonic()
                response = primary_call()
                elapsed = time.monotonic() - start

                result = FallbackResult(
                    success=True,
                    response=response,
                    model_used=entry.model,
                    provider_used=entry.provider,
                    attempts=attempts,
                )
                logger.info(
                    "Fallback chain succeeded on %s in %.2fs",
                    label, elapsed,
                )
                return result

            except retryable_errors as exc:
                elapsed = time.monotonic() - start
                error_info = {
                    "model": entry.model,
                    "provider": entry.provider,
                    "attempt": attempt_num,
                    "error": str(exc),
                    "elapsed_seconds": round(elapsed, 2),
                }
                attempts.append(error_info)
                logger.warning(
                    "Fallback attempt %s [%d/%d] failed: %s",
                    label, attempt_num, max_retries_per_model, exc,
                )

                if attempt_num < max_retries_per_model:
                    wait = min(2 ** attempt_num, 30)
                    logger.info("Retrying %s in %ds...", label, wait)
                    time.sleep(wait)
            except Exception as exc:
                # Non-retryable error — stop immediately
                error_info = {
                    "model": entry.model,
                    "provider": entry.provider,
                    "attempt": attempt_num,
                    "error": f"Non-retryable: {exc}",
                    "elapsed_seconds": 0,
                }
                attempts.append(error_info)
                return FallbackResult(
                    success=False,
                    error=str(exc),
                    attempts=attempts,
                )

    # All entries exhausted
    last_error = attempts[-1]["error"] if attempts else "All models in chain failed"
    logger.error("Fallback chain exhausted: %s", last_error)
    return FallbackResult(success=False, error=last_error, attempts=attempts)


def get_fallback_model_info() -> list[dict[str, str]]:
    """Get a human-readable list of configured fallback models."""
    chain = _load_fallback_chain()
    return [
        {"index": str(i), "provider": e.provider, "model": e.model}
        for i, e in enumerate(chain, 1)
    ]
