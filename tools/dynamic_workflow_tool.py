#!/usr/bin/env python3
"""
Dynamic Workflow Tool

Provides ``dynamic_workflow`` — a core tool that lets the agent decompose
complex goals into parallel sub-tasks executed across many subagents with
automatic verification and convergence.

Also provides ``workflow_status`` and ``workflow_cancel`` for lifecycle
management.

Usage:
    dynamic_workflow(
        goal="Refactor the entire auth module to use OAuth2",
        max_agents=20,
        verify=True
    )
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from tools.registry import registry, tool_error, tool_result
from tools.workflow_orchestrator import (
    get_orchestrator,
    execute_workflow,
    get_workflow_status,
    cancel_workflow,
    list_workflows,
    DEFAULT_MAX_PARALLEL_AGENTS,
    DEFAULT_MAX_CONVERGENCE_ROUNDS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _get_max_parallel_from_config() -> int:
    try:
        from alex_cli.config import read_raw_config
        cfg = read_raw_config()
        wf_cfg = cfg.get("workflow", {})
        if isinstance(wf_cfg, dict):
            return max(1, int(wf_cfg.get("max_parallel_agents", DEFAULT_MAX_PARALLEL_AGENTS)))
    except Exception:
        pass
    return DEFAULT_MAX_PARALLEL_AGENTS


def _get_max_rounds_from_config() -> int:
    try:
        from alex_cli.config import read_raw_config
        cfg = read_raw_config()
        wf_cfg = cfg.get("workflow", {})
        if isinstance(wf_cfg, dict):
            return max(1, int(wf_cfg.get("max_convergence_rounds", DEFAULT_MAX_CONVERGENCE_ROUNDS)))
    except Exception:
        pass
    return DEFAULT_MAX_CONVERGENCE_ROUNDS

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DYNAMIC_WORKFLOW_SCHEMA: Dict[str, Any] = {
    "name": "dynamic_workflow",
    "description": (
        "Decompose a complex goal into parallel sub-tasks executed across "
        "multiple subagents simultaneously. Automatically verifies results "
        "and iterates until convergence. Use this for large-scale tasks that "
        "benefit from parallel execution: codebase-wide refactors, multi-file "
        "reviews, security audits, research across many sources.\n\n"
        "The system will:\n"
        "  1. Plan: decompose your goal into independent sub-tasks\n"
        "  2. Execute: run sub-tasks in parallel across N agents\n"
        "  3. Verify: check each result for correctness\n"
        "  4. Iterate: re-run failed tasks, converge on quality\n"
        "  5. Merge: combine all results into a final answer\n\n"
        "Returns a workflow_id immediately. Poll with workflow_status "
        "to check progress and get the final answer when converged."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The high-level goal to decompose and execute in parallel."
            },
            "max_agents": {
                "type": "integer",
                "description": "Maximum parallel subagents to use (default: config value, max 500).",
                "default": 20,
            },
            "verify": {
                "type": "boolean",
                "description": "Whether to run verification on each sub-task result (default: true).",
                "default": True,
            },
            "context": {
                "type": "string",
                "description": "Optional context or background information to include in every sub-task.",
                "default": "",
            },
        },
        "required": ["goal"],
    },
}

WORKFLOW_STATUS_SCHEMA: Dict[str, Any] = {
    "name": "workflow_status",
    "description": (
        "Check the status of a running or completed dynamic workflow. "
        "Returns task progress, convergence round, duration, and the final "
        "answer when the workflow has converged."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "The workflow ID returned by dynamic_workflow.",
            },
        },
        "required": ["workflow_id"],
    },
}

WORKFLOW_CANCEL_SCHEMA: Dict[str, Any] = {
    "name": "workflow_cancel",
    "description": "Cancel a running dynamic workflow. All running sub-tasks will be interrupted.",
    "parameters": {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "The workflow ID to cancel.",
            },
        },
        "required": ["workflow_id"],
    },
}

WORKFLOW_LIST_SCHEMA: Dict[str, Any] = {
    "name": "workflow_list",
    "description": "List all active and recently completed dynamic workflows.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def dynamic_workflow(
    goal: str,
    max_agents: int = 20,
    verify: bool = True,
    context: str = "",
    task_id: Optional[str] = None,
) -> str:
    if not goal or not isinstance(goal, str):
        return tool_error("'goal' is required and must be a string")

    if max_agents < 1:
        max_agents = 1
    max_agents = min(max_agents, 500)

    try:
        workflow_id = execute_workflow(goal)
        return tool_result({
            "success": True,
            "workflow_id": workflow_id,
            "goal": goal[:200],
            "max_agents": max_agents,
            "verify": verify,
            "message": (
                f"Workflow {workflow_id} started with up to {max_agents} parallel agents. "
                f"Use workflow_status(workflow_id='{workflow_id}') to check progress."
            ),
        })
    except Exception as exc:
        logger.exception("dynamic_workflow failed")
        return tool_error(f"Workflow failed to start: {type(exc).__name__}: {exc}")


def workflow_status(
    workflow_id: str,
    task_id: Optional[str] = None,
) -> str:
    if not workflow_id:
        return tool_error("'workflow_id' is required")
    return get_workflow_status(workflow_id)


def workflow_cancel(
    workflow_id: str,
    task_id: Optional[str] = None,
) -> str:
    if not workflow_id:
        return tool_error("'workflow_id' is required")
    return cancel_workflow(workflow_id)


def workflow_list(
    task_id: Optional[str] = None,
) -> str:
    return list_workflows()

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _workflow_check() -> bool:
    """Workflow tools are always available (no external dependencies)."""
    return True


registry.register(
    name="dynamic_workflow",
    toolset="workflow",
    schema=DYNAMIC_WORKFLOW_SCHEMA,
    handler=lambda args, **kw: dynamic_workflow(
        goal=args.get("goal", ""),
        max_agents=args.get("max_agents", 20),
        verify=args.get("verify", True),
        context=args.get("context", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=_workflow_check,
    emoji="⚡",
)

registry.register(
    name="workflow_status",
    toolset="workflow",
    schema=WORKFLOW_STATUS_SCHEMA,
    handler=lambda args, **kw: workflow_status(
        workflow_id=args.get("workflow_id", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=_workflow_check,
    emoji="📊",
)

registry.register(
    name="workflow_cancel",
    toolset="workflow",
    schema=WORKFLOW_CANCEL_SCHEMA,
    handler=lambda args, **kw: workflow_cancel(
        workflow_id=args.get("workflow_id", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=_workflow_check,
    emoji="⏹️",
)

registry.register(
    name="workflow_list",
    toolset="workflow",
    schema=WORKFLOW_LIST_SCHEMA,
    handler=lambda args, **kw: workflow_list(
        task_id=kw.get("task_id"),
    ),
    check_fn=_workflow_check,
    emoji="📋",
)
