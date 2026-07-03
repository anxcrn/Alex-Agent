"""Per-agent spend caps — budget enforcement for cost control.

Tracks and enforces per-session and per-subagent cost limits.
Configurable via ``budget`` section in ``config.yaml``::

    budget:
      max_cost_usd: 0              # 0 = no limit
      max_cost_per_subagent_usd: 0 # 0 = no limit
      warn_at_percent: 80          # warn at this % of total budget

Integration:
    Called from ``run_agent.py`` after each API call to check the running
    cost against configured limits.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cost tracking (persistent across restarts via JSON sidecar)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_session_costs: dict[str, float] = {}
_subagent_costs: dict[str, float] = {}
_total_cost: float = 0.0
_cost_file = Path("~/.alex/spend_caps.json").expanduser()


def _load_persistent_costs() -> None:
    global _total_cost, _session_costs, _subagent_costs
    if not _cost_file.exists():
        return
    try:
        data = json.loads(_cost_file.read_text(encoding="utf-8"))
        with _lock:
            _total_cost = data.get("total_cost", 0.0)
            _session_costs = data.get("session_costs", {})
            _subagent_costs = data.get("subagent_costs", {})
    except Exception as exc:
        logger.debug("Failed to load spend caps: %s", exc)


def _save_persistent_costs() -> None:
    try:
        _cost_file.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            data = {
                "total_cost": _total_cost,
                "session_costs": _session_costs,
                "subagent_costs": _subagent_costs,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        _cost_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("Failed to save spend caps: %s", exc)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


@dataclass
class BudgetConfig:
    max_cost_usd: float = 0.0
    max_cost_per_subagent_usd: float = 0.0
    warn_at_percent: float = 80.0

    @classmethod
    def from_config(cls) -> "BudgetConfig":
        try:
            from alex_cli.config import load_config
            config = load_config()
            budget = config.get("budget", {})
            return cls(
                max_cost_usd=float(budget.get("max_cost_usd", 0)),
                max_cost_per_subagent_usd=float(budget.get("max_cost_per_subagent_usd", 0)),
                warn_at_percent=float(budget.get("warn_at_percent", 80)),
            )
        except Exception:
            return cls()


# ---------------------------------------------------------------------------
# Tracking API
# ---------------------------------------------------------------------------


def record_cost(
    session_id: str,
    cost_usd: float,
    is_subagent: bool = False,
    subagent_id: str = "",
) -> dict[str, Any]:
    """Record a model API call cost.

    Args:
        session_id: The session to attribute the cost to.
        cost_usd: The cost in USD of the API call.
        is_subagent: Whether this is a subagent's cost.
        subagent_id: The subagent ID if ``is_subagent`` is True.

    Returns:
        Dict with budget status: ``{"within_budget": bool, "total_cost": float,
        "warning": str, "remaining": float}``.
    """
    global _total_cost
    budget = BudgetConfig.from_config()

    with _lock:
        _total_cost += cost_usd
        _session_costs[session_id] = _session_costs.get(session_id, 0.0) + cost_usd
        if is_subagent and subagent_id:
            _subagent_costs[subagent_id] = _subagent_costs.get(subagent_id, 0.0) + cost_usd

    # Persist periodically (every 10 records)
    _save_persistent_costs()

    # Check budget limits
    result: dict[str, Any] = {
        "total_cost": _total_cost,
        "session_cost": _session_costs.get(session_id, 0.0),
        "within_budget": True,
        "warning": "",
        "remaining": float("inf"),
    }

    if budget.max_cost_usd > 0:
        remaining = budget.max_cost_usd - _total_cost
        result["remaining"] = remaining
        if remaining <= 0:
            result["within_budget"] = False
            result["warning"] = f"Total budget of ${budget.max_cost_usd:.2f} exhausted"
            logger.warning("Budget exhausted: total=$%.4f, limit=$%.2f", _total_cost, budget.max_cost_usd)
        elif _total_cost / budget.max_cost_usd * 100 >= budget.warn_at_percent:
            pct = _total_cost / budget.max_cost_usd * 100
            result["warning"] = f"Budget at {pct:.0f}% (${_total_cost:.4f}/${budget.max_cost_usd:.2f})"
            logger.info("Budget warning: %.1f%% used", pct)

    # Check per-subagent budget
    if is_subagent and subagent_id and budget.max_cost_per_subagent_usd > 0:
        subagent_cost = _subagent_costs.get(subagent_id, 0.0)
        if subagent_cost > budget.max_cost_per_subagent_usd:
            result["within_budget"] = False
            result["warning"] = (
                f"Subagent budget of ${budget.max_cost_per_subagent_usd:.2f} "
                f"exceeded (${subagent_cost:.4f})"
            )

    return result


def get_session_cost(session_id: str) -> float:
    """Get the total cost for a session."""
    with _lock:
        return _session_costs.get(session_id, 0.0)


def get_total_cost() -> float:
    """Get the total cost across all sessions."""
    with _lock:
        return _total_cost


def get_cost_summary() -> dict[str, Any]:
    """Get a summary of all costs."""
    with _lock:
        return {
            "total_cost_usd": round(_total_cost, 6),
            "session_count": len(_session_costs),
            "largest_session": max(_session_costs.values()) if _session_costs else 0.0,
            "subagent_count": len(_subagent_costs),
        }


def is_within_budget() -> bool:
    """Check if the current spend is within configured budget."""
    budget = BudgetConfig.from_config()
    with _lock:
        if budget.max_cost_usd > 0 and _total_cost >= budget.max_cost_usd:
            return False
    return True


def check_budget(agent_type: str = "main", subagent_id: str = "") -> tuple[bool, str]:
    """Check whether a new agent call is within budget.

    Returns:
        Tuple of ``(allowed: bool, reason: str)``.
    """
    if not is_within_budget():
        budget = BudgetConfig.from_config()
        return False, f"Total budget ${budget.max_cost_usd:.2f} exhausted"

    if agent_type == "subagent" and subagent_id:
        budget = BudgetConfig.from_config()
        if budget.max_cost_per_subagent_usd > 0:
            subagent_cost = 0.0
            with _lock:
                subagent_cost = _subagent_costs.get(subagent_id, 0.0)
            if subagent_cost >= budget.max_cost_per_subagent_usd:
                return False, (
                    f"Subagent budget ${budget.max_cost_per_subagent_usd:.2f} "
                    f"exhausted (${subagent_cost:.4f})"
                )

    return True, ""


# Load persistent costs at import time
_load_persistent_costs()
