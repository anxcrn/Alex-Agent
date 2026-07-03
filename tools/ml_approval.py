"""ML-driven auto-approval for dangerous commands and code execution.

Extends the existing ``_smart_approve()`` in ``tools/approval.py`` with a
dedicated fast auxiliary model and configurable policy.

Architecture::

    check_all_command_guards()
      └─ Phase 2.5: approvals.mode == "smart"
           └─ _smart_approve()  ← existing hook in tools/approval.py
                └─ ml_approve() ← this module (plugs in via config)

Behaviour:
  1. A fast auxiliary model evaluates the command + context.
  2. Returns ``approve``, ``deny``, or ``escalate`` (→ manual prompt).
  3. Auto-learned patterns are cached to bypass the model on repeat matches.
  4. Confidence thresholds are configurable per sensitivity level.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIDENCE_THRESHOLD = 0.85
DEFAULT_DENY_THRESHOLD = 0.95
LEARNED_PATTERNS_PATH = "~/.alex/ml_approval_patterns.json"
MAX_CACHE_SIZE = 500
MODEL_TIMEOUT_S = 15

# ---------------------------------------------------------------------------
# Cached learned patterns (persistent across restarts)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_learned_patterns: dict[str, str] = {}  # command_hash -> "approve"/"deny"
_learned_exact: set[str] = set()        # exact command strings that are auto-approved
_learned_deny: set[str] = set()         # exact command strings that are auto-denied


def _load_learned_patterns() -> None:
    global _learned_patterns, _learned_exact, _learned_deny
    path = Path(LEARNED_PATTERNS_PATH).expanduser()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        with _lock:
            _learned_patterns = data.get("patterns", {})
            _learned_exact = set(data.get("approved_exact", []))
            _learned_deny = set(data.get("denied_exact", []))
    except Exception as exc:
        logger.warning("Failed to load ML approval patterns: %s", exc)


def _save_learned_patterns() -> None:
    path = Path(LEARNED_PATTERNS_PATH).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            data = {
                "patterns": dict(list(_learned_patterns.items())[:MAX_CACHE_SIZE]),
                "approved_exact": list(_learned_exact)[:MAX_CACHE_SIZE],
                "denied_exact": list(_learned_deny)[:MAX_CACHE_SIZE],
            }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save ML approval patterns: %s", exc)


def _command_hash(command: str) -> str:
    import hashlib
    return hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]


def _check_pattern_cache(command: str) -> str | None:
    """Check if a command matches a cached pattern.
    Returns ``approve``, ``deny``, or ``None`` (no match).
    """
    with _lock:
        if command in _learned_exact:
            return "approve"
        if command in _learned_deny:
            return "deny"
        ch = _command_hash(command)
        if ch in _learned_patterns:
            return _learned_patterns[ch]
    return None


def _record_pattern(command: str, decision: str) -> None:
    """Record a learned pattern for future automatic decisions."""
    with _lock:
        ch = _command_hash(command)
        _learned_patterns[ch] = decision
        if len(_learned_patterns) > MAX_CACHE_SIZE * 2:
            trimmed = dict(list(_learned_patterns.items())[:MAX_CACHE_SIZE])
            _learned_patterns.clear()
            _learned_patterns.update(trimmed)
    _save_learned_patterns()


def _record_exact(command: str, decision: str) -> None:
    """Record an exact command match."""
    with _lock:
        if decision == "approve":
            _learned_exact.add(command)
        else:
            _learned_deny.add(command)
    _save_learned_patterns()


# ---------------------------------------------------------------------------
# ML evaluation
# ---------------------------------------------------------------------------

@dataclass
class MLEvaluation:
    decision: str  # "approve", "deny", "escalate"
    confidence: float
    reason: str = ""
    model_used: str = ""


def _call_auxiliary_model(
    command: str,
    description: str,
    env_type: str = "",
    model_config: dict[str, Any] | None = None,
) -> MLEvaluation:
    """Call the auxiliary LLM to evaluate a command.

    Uses the configured ``security.auto_approval_model`` or falls back to
    the existing auxiliary approval client.
    """
    config = model_config or {}

    # Build the evaluation prompt
    prompt = f"""You are a security evaluation assistant. Assess whether the following command is safe to execute.

Context:
- Environment: {env_type or "local terminal"}
- Description: {description}
- Command: {command}

Evaluate based on:
1. Destructive potential (file deletion, data loss, system modification)
2. Security risk (credential exposure, privilege escalation, network attacks)
3. Irreversibility (can the action be undone?)
4. Intent alignment (does this match typical development/operations tasks?)

Respond in JSON format with exactly these fields:
- "decision": one of "approve" (safe to run), "deny" (unsafe, block), "escalate" (uncertain, ask human)
- "confidence": a float between 0.0 and 1.0
- "reason": brief explanation for the decision

JSON:"""

    try:
        from agent.auxiliary_client import AuxiliaryClient

        client = AuxiliaryClient()
        response = client.call_llm(
            task="approval",
            prompt=prompt,
            response_format="json",
            model=config.get("model", ""),
            provider=config.get("provider", ""),
            base_url=config.get("base_url", ""),
            timeout=MODEL_TIMEOUT_S,
        )

        raw = response.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("\n", 1)[0]
        data = json.loads(raw) if raw else {}

        decision = data.get("decision", "escalate")
        confidence = float(data.get("confidence", 0.0))
        reason = data.get("reason", "")

        if decision not in ("approve", "deny", "escalate"):
            decision = "escalate"

        return MLEvaluation(
            decision=decision,
            confidence=confidence,
            reason=reason,
            model_used=config.get("model", "auxiliary-approval"),
        )
    except Exception as exc:
        logger.warning("ML approval model call failed: %s", exc)
        return MLEvaluation(
            decision="escalate",
            confidence=0.0,
            reason=f"Model call failed: {exc}",
            model_used="none",
        )


def ml_approve(
    command: str,
    description: str,
    env_type: str = "",
    *,
    model_config: dict[str, Any] | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    deny_threshold: float = DEFAULT_DENY_THRESHOLD,
) -> str:
    """Evaluate a command for auto-approval using ML.

    Args:
        command: The full command string.
        description: Human-readable description of the risk.
        env_type: Execution environment type (local, docker, etc.).
        model_config: Override model/provider/base_url for the auxiliary call.
        confidence_threshold: Minimum confidence to auto-approve (default 0.85).
        deny_threshold: Minimum confidence to auto-deny (default 0.95).

    Returns:
        ``approve``, ``deny``, or ``escalate`` (→ manual prompt).
    """
    # Check pattern cache first
    cached = _check_pattern_cache(command)
    if cached:
        logger.debug("ML approval cache hit: %s for %r", cached, command[:80])
        return cached

    # Call the auxiliary model
    eval_result = _call_auxiliary_model(command, description, env_type, model_config)

    if eval_result.decision == "approve" and eval_result.confidence >= confidence_threshold:
        _record_pattern(command, "approve")
        logger.info(
            "ML auto-approved (confidence=%.3f, reason=%s): %r",
            eval_result.confidence,
            eval_result.reason,
            command[:80],
        )
        return "approve"

    if eval_result.decision == "deny" and eval_result.confidence >= deny_threshold:
        _record_pattern(command, "deny")
        logger.info(
            "ML auto-denied (confidence=%.3f, reason=%s): %r",
            eval_result.confidence,
            eval_result.reason,
            command[:80],
        )
        return "deny"

    # Low confidence or uncertain → escalate to human
    logger.info(
        "ML escalated (decision=%s, confidence=%.3f): %r",
        eval_result.decision,
        eval_result.confidence,
        command[:80],
    )
    return "escalate"


# Load learned patterns at import time
_load_learned_patterns()
