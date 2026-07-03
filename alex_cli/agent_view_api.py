"""Agent View API — real-time agent activity tracking and session monitoring.

Provides REST endpoints and WebSocket-based real-time updates for:
- Active agent sessions
- Running workflows and their progress
- Tool call activity feed
- Token usage and cost tracking
- Agent state transitions

Integrated into the dashboard web server via ``include_router``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory activity store (replace with SQLite/Redis for production)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_agent_activities: list[dict[str, Any]] = []
_tool_call_log: list[dict[str, Any]] = []
_active_sessions: dict[str, dict[str, Any]] = {}
_max_activities = 500
_max_tool_logs = 1000


def record_activity(
    session_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Record an agent activity event."""
    entry = {
        "session_id": session_id,
        "event_type": event_type,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _agent_activities.append(entry)
        if len(_agent_activities) > _max_activities:
            _agent_activities.pop(0)


def record_tool_call(
    session_id: str,
    tool_name: str,
    status: str,
    duration_ms: float = 0.0,
    cost_usd: float = 0.0,
    error: str = "",
) -> None:
    """Record a tool call event."""
    entry = {
        "session_id": session_id,
        "tool_name": tool_name,
        "status": status,
        "duration_ms": duration_ms,
        "cost_usd": cost_usd,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _tool_call_log.append(entry)
        if len(_tool_call_log) > _max_tool_logs:
            _tool_call_log.pop(0)


def register_session(session_id: str, metadata: dict[str, Any] | None = None) -> None:
    """Register a new active session."""
    with _lock:
        _active_sessions[session_id] = {
            "session_id": session_id,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "tool_calls": 0,
            "cost_usd": 0.0,
            "total_duration_ms": 0.0,
            **(metadata or {}),
        }


def update_session(session_id: str, **kwargs: Any) -> None:
    """Update an active session's fields."""
    with _lock:
        if session_id in _active_sessions:
            _active_sessions[session_id].update(kwargs)


def complete_session(
    session_id: str,
    status: str = "completed",
    cost_usd: float = 0.0,
) -> None:
    """Mark a session as completed."""
    with _lock:
        if session_id in _active_sessions:
            session = _active_sessions[session_id]
            session["status"] = status
            session["completed_at"] = datetime.now(timezone.utc).isoformat()
            session["cost_usd"] = cost_usd
            if "started_at" in session:
                start = datetime.fromisoformat(session["started_at"])
                session["total_duration_ms"] = (
                    datetime.now(timezone.utc) - start
                ).total_seconds() * 1000


def get_activities(
    limit: int = 50,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    """Get recent agent activities."""
    with _lock:
        result = list(_agent_activities)
    if event_type:
        result = [a for a in result if a["event_type"] == event_type]
    return result[-limit:]


def get_tool_call_log(
    limit: int = 50,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get recent tool call logs."""
    with _lock:
        result = list(_tool_call_log)
    if session_id:
        result = [t for t in result if t["session_id"] == session_id]
    return result[-limit:]


def get_active_sessions() -> list[dict[str, Any]]:
    """Get all currently active sessions."""
    with _lock:
        return [
            s for s in _active_sessions.values()
            if s.get("status") in ("running", "pending")
        ]


def get_session_summary() -> dict[str, Any]:
    """Get summary statistics for the agent view dashboard."""
    with _lock:
        total_sessions = len(_active_sessions)
        active = sum(
            1 for s in _active_sessions.values()
            if s.get("status") == "running"
        )
        total_tool_calls = len(_tool_call_log)
        total_cost = sum(
            s.get("cost_usd", 0.0) for s in _active_sessions.values()
        )
        recent_errors = sum(
            1 for t in _tool_call_log[-200:]
            if t.get("status") == "error"
        )
    return {
        "total_sessions": total_sessions,
        "active_sessions": active,
        "total_tool_calls": total_tool_calls,
        "total_cost_usd": round(total_cost, 6),
        "recent_errors": recent_errors,
        "uptime_seconds": time.time() - _agent_view_start_time,
    }


_agent_view_start_time = time.time()

# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = None


def create_router():
    """Create and return the Agent View API router."""
    global router
    if router is not None:
        return router

    try:
        from fastapi import APIRouter, HTTPException, Query
        from pydantic import BaseModel
    except ImportError:
        return None

    router = APIRouter(prefix="/api/v1/agent-view", tags=["agent-view"])

    @router.get("/summary")
    async def view_summary():
        return get_session_summary()

    @router.get("/activities")
    async def view_activities(
        limit: int = Query(50, ge=1, le=500),
        event_type: str | None = Query(None),
    ):
        return {"activities": get_activities(limit=limit, event_type=event_type)}

    @router.get("/tool-calls")
    async def view_tool_calls(
        limit: int = Query(50, ge=1, le=500),
        session_id: str | None = Query(None),
    ):
        return {"tool_calls": get_tool_call_log(limit=limit, session_id=session_id)}

    @router.get("/sessions")
    async def view_sessions():
        return {
            "sessions": get_active_sessions(),
            "total_sessions": len(get_active_sessions()),
        }

    @router.get("/sessions/{session_id}")
    async def view_session_detail(session_id: str):
        with _lock:
            session = _active_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        tool_calls = get_tool_call_log(limit=100, session_id=session_id)
        return {"session": session, "tool_calls": tool_calls}

    return router
