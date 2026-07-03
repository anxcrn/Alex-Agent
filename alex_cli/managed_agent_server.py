"""Managed Agents HTTP API server.

Provides a FastAPI-based REST API for running agents programmatically.
Supports synchronous execution, streaming, and session management.

Usage::

    alex managed-agent start --port 8080
    curl -X POST http://localhost:8080/v1/agents/run -H "Content-Type: application/json" \\
         -d '{"prompt": "What is 2+2?"}'
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory session store (production: replace with SQLite/Redis)
# ---------------------------------------------------------------------------

_running_agents: dict[str, "_ManagedAgentSession"] = {}
_lock = threading.Lock()


class SessionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class _ManagedAgentSession:
    id: str
    status: SessionStatus = SessionStatus.PENDING
    prompt: str = ""
    result: str = ""
    error: str = ""
    model: str = ""
    provider: str = ""
    created_at: str = ""
    completed_at: str = ""
    iterations_used: int = 0
    total_cost_usd: float = 0.0
    thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


def _run_agent_in_thread(session: _ManagedAgentSession) -> None:
    """Run an agent in a background thread and store results in the session."""
    try:
        from run_agent import AIAgent

        agent = AIAgent(
            model=session.model or "",
            provider=session.provider or "",
            max_iterations=90,
            quiet_mode=True,
        )

        with _lock:
            session.status = SessionStatus.RUNNING

        result = agent.run_conversation(user_message=session.prompt)
        final_response = result.get("final_response", "")

        with _lock:
            session.status = SessionStatus.COMPLETED
            session.result = final_response
            session.completed_at = datetime.now(timezone.utc).isoformat()
            session.iterations_used = result.get("iterations_used", 0)
            session.total_cost_usd = result.get("total_cost_usd", 0.0)
    except Exception as exc:
        with _lock:
            session.status = SessionStatus.FAILED
            session.error = str(exc)
            session.completed_at = datetime.now(timezone.utc).isoformat()


def _get_session(session_id: str) -> _ManagedAgentSession | None:
    with _lock:
        return _running_agents.get(session_id)


def _list_sessions() -> list[_ManagedAgentSession]:
    with _lock:
        return list(_running_agents.values())


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: Any):
    logger.info("Managed Agents API starting")
    yield
    # Cancel all running agents on shutdown
    with _lock:
        for sid, session in _running_agents.items():
            if session.status == SessionStatus.RUNNING:
                session.cancel_event.set()
    logger.info("Managed Agents API stopped")


def create_app() -> Any:
    """Create and return the FastAPI application."""
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel
    except ImportError:
        print("fastapi and uvicorn are required. Install with: pip install 'alex-agent[web]'")
        raise

    app = FastAPI(
        title="Alex Managed Agents API",
        version="1.0.0",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Request / Response models
    # -----------------------------------------------------------------------

    class RunRequest(BaseModel):
        prompt: str
        model: str = ""
        provider: str = ""
        max_iterations: int = 90
        toolsets: list[str] | None = None
        system_prompt: str = ""
        timeout_seconds: int = 300
        webhook_url: str = ""
        webhook_events: list[str] = ["completed", "failed"]

    class RunResponse(BaseModel):
        session_id: str
        status: str

    class StatusResponse(BaseModel):
        session_id: str
        status: str
        result: str = ""
        error: str = ""
        created_at: str = ""
        completed_at: str = ""
        iterations_used: int = 0
        total_cost_usd: float = 0.0

    class HealthResponse(BaseModel):
        status: str
        uptime_seconds: float
        active_sessions: int

    # -----------------------------------------------------------------------
    # API key validation
    # -----------------------------------------------------------------------

    def _check_auth(request: Request) -> None:
        config_key = ""
        try:
            import alex_cli.config as cfg
            config = cfg.load_config()
            config_key = config.get("managed_agents", {}).get("api_key", "")
        except Exception:
            pass
        if not config_key:
            return
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:] == config_key:
            return
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # -----------------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------------

    @app.get("/v1/health")
    async def health(request: Request) -> dict:
        return {
            "status": "ok",
            "uptime_seconds": time.time() - _start_time,
            "active_sessions": len(_list_sessions()),
            "version": "1.0.0",
        }

    @app.post("/v1/agents/run", response_model=RunResponse)
    async def run_agent(request: Request, body: RunRequest) -> dict:
        _check_auth(request)

        session_id = f"agent-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        session = _ManagedAgentSession(
            id=session_id,
            status=SessionStatus.PENDING,
            prompt=body.prompt,
            model=body.model,
            provider=body.provider,
            created_at=now,
        )

        with _lock:
            _running_agents[session_id] = session

        thread = threading.Thread(
            target=_run_agent_in_thread,
            args=(session,),
            daemon=True,
        )
        with _lock:
            session.thread = thread
        thread.start()

        return {"session_id": session_id, "status": "pending"}

    @app.get("/v1/agents/{session_id}/status", response_model=StatusResponse)
    async def agent_status(request: Request, session_id: str) -> dict:
        _check_auth(request)
        session = _get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        with _lock:
            return {
                "session_id": session.id,
                "status": session.status.value,
                "result": session.result,
                "error": session.error,
                "created_at": session.created_at,
                "completed_at": session.completed_at,
                "iterations_used": session.iterations_used,
                "total_cost_usd": session.total_cost_usd,
            }

    @app.post("/v1/agents/{session_id}/cancel")
    async def cancel_agent(request: Request, session_id: str) -> dict:
        _check_auth(request)
        session = _get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        with _lock:
            if session.status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED):
                return {"session_id": session_id, "status": session.status.value}

            session.cancel_event.set()
            session.status = SessionStatus.CANCELLED
            session.completed_at = datetime.now(timezone.utc).isoformat()

        return {"session_id": session_id, "status": "cancelled"}

    @app.get("/v1/agents")
    async def list_agents(request: Request) -> list[dict]:
        _check_auth(request)
        sessions = _list_sessions()
        return [
            {
                "session_id": s.id,
                "status": s.status.value,
                "created_at": s.created_at,
                "completed_at": s.completed_at,
            }
            for s in sessions
        ]

    return app


_start_time = time.time()


def start_server(port: int = 8080, host: str = "127.0.0.1") -> None:
    """Start the Managed Agents HTTP API server."""
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required. Install with: pip install 'alex-agent[web]'")
        raise

    app = create_app()
    logger.info("Starting Managed Agents API on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
