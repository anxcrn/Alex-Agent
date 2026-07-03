"""Session crash recovery — periodic state checkpointing and recovery.

Periodically saves the agent's state (conversation history, iteration count,
active tool calls) to disk so it can resume after a crash or restart.

Checkpoint format: JSON files in ``~/.alex/checkpoints/{session_id}/``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CHECKPOINT_INTERVAL = 30  # seconds
_MAX_CHECKPOINTS = 10
_CHECKPOINT_LOCK = threading.Lock()
_checkpoint_timers: dict[str, threading.Timer] = {}


def _get_checkpoint_dir(session_id: str) -> Path:
    from alex_constants import get_alex_home
    path = Path(get_alex_home()) / "checkpoints" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _checkpoint_path(session_id: str, seq: int = 0) -> Path:
    return _get_checkpoint_dir(session_id) / f"checkpoint-{seq:04d}.json"


def _checkpoint_index_path(session_id: str) -> Path:
    return _get_checkpoint_dir(session_id) / "index.json"


def save_checkpoint(
    session_id: str,
    state: dict[str, Any],
    *,
    force: bool = False,
) -> str:
    """Save a checkpoint of the agent's state.

    Args:
        session_id: The session to checkpoint.
        state: Serializable dict with conversation history, iteration count, etc.
        force: Force save even if the interval hasn't elapsed.

    Returns:
        Path to the checkpoint file.
    """
    dir_path = _get_checkpoint_dir(session_id)

    # Load index to get next sequence number
    index_path = _checkpoint_index_path(session_id)
    index: dict[str, Any] = {"sequence": 0, "checkpoints": []}
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            index = {"sequence": 0, "checkpoints": []}

    seq = index.get("sequence", 0) + 1
    ts = datetime.now(timezone.utc).isoformat()

    checkpoint = {
        "session_id": session_id,
        "sequence": seq,
        "timestamp": ts,
        "state": state,
    }

    ckpt_path = _checkpoint_path(session_id, seq)
    ckpt_path.write_text(json.dumps(checkpoint, indent=2, default=str), encoding="utf-8")

    # Update index
    index["sequence"] = seq
    index["last_checkpoint"] = ts
    index["checkpoints"].append({
        "seq": seq,
        "timestamp": ts,
        "path": str(ckpt_path),
    })

    # Prune old checkpoints
    while len(index["checkpoints"]) > _MAX_CHECKPOINTS:
        oldest = index["checkpoints"].pop(0)
        try:
            Path(oldest["path"]).unlink()
        except OSError:
            pass

    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    logger.debug("Checkpoint %d saved for session %s", seq, session_id)
    return str(ckpt_path)


def load_latest_checkpoint(session_id: str) -> dict[str, Any] | None:
    """Load the most recent checkpoint for a session.

    Returns:
        The checkpoint state dict, or ``None`` if no checkpoint exists.
    """
    index_path = _checkpoint_index_path(session_id)
    if not index_path.exists():
        return None

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        checkpoints = index.get("checkpoints", [])
        if not checkpoints:
            return None

        latest = checkpoints[-1]
        ckpt_path = Path(latest["path"])
        if not ckpt_path.exists():
            return None

        data = json.loads(ckpt_path.read_text(encoding="utf-8"))
        return data.get("state")
    except Exception as exc:
        logger.warning("Failed to load checkpoint for %s: %s", session_id, exc)
        return None


def list_checkpoints(session_id: str) -> list[dict[str, Any]]:
    """List all available checkpoints for a session."""
    index_path = _checkpoint_index_path(session_id)
    if not index_path.exists():
        return []
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        return index.get("checkpoints", [])
    except Exception:
        return []


def delete_checkpoints(session_id: str) -> bool:
    """Delete all checkpoints for a session."""
    dir_path = _get_checkpoint_dir(session_id)
    if not dir_path.exists():
        return True
    try:
        shutil.rmtree(dir_path)
        logger.info("Deleted checkpoints for session %s", session_id)
        return True
    except Exception as exc:
        logger.warning("Failed to delete checkpoints for %s: %s", session_id, exc)
        return False


def start_auto_checkpoint(
    session_id: str,
    state_provider: Any,
    interval: int = _CHECKPOINT_INTERVAL,
) -> None:
    """Start periodic checkpointing for a session.

    Args:
        session_id: The session to checkpoint.
        state_provider: A callable that returns the current state dict, or a
            dict (called once). If a dict, it is updated in-place on each tick.
        interval: Seconds between checkpoints.
    """
    def _tick(sid: str, provider: Any) -> None:
        try:
            if callable(provider):
                state = provider()
            else:
                state = dict(provider)
            save_checkpoint(sid, state)
        except Exception as exc:
            logger.debug("Auto-checkpoint error for %s: %s", sid, exc)
        finally:
            _schedule_next(sid, provider, interval)

    _schedule_next(session_id, state_provider, interval)
    logger.info("Auto-checkpoint started for %s (every %ds)", session_id, interval)


def _schedule_next(session_id: str, state_provider: Any, interval: int) -> None:
    timer = threading.Timer(interval, _auto_checkpoint_tick, args=[session_id, state_provider, interval])
    timer.daemon = True
    timer.name = f"ckpt-{session_id[:8]}"
    with _CHECKPOINT_LOCK:
        old = _checkpoint_timers.pop(session_id, None)
        if old:
            old.cancel()
        _checkpoint_timers[session_id] = timer
    timer.start()


def _auto_checkpoint_tick(session_id: str, state_provider: Any, interval: int) -> None:
    try:
        state = state_provider() if callable(state_provider) else dict(state_provider)
        save_checkpoint(session_id, state)
    except Exception as exc:
        logger.debug("Auto-checkpoint: %s", exc)
    finally:
        _schedule_next(session_id, state_provider, interval)


def stop_auto_checkpoint(session_id: str) -> None:
    """Stop periodic checkpointing for a session."""
    with _CHECKPOINT_LOCK:
        timer = _checkpoint_timers.pop(session_id, None)
        if timer:
            timer.cancel()
            logger.debug("Auto-checkpoint stopped for %s", session_id)


def get_checkpoint_status(session_id: str) -> dict[str, Any]:
    """Get checkpoint status for a session."""
    index_path = _checkpoint_index_path(session_id)
    if not index_path.exists():
        return {"has_checkpoints": False, "checkpoint_count": 0}
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        return {
            "has_checkpoints": True,
            "checkpoint_count": len(index.get("checkpoints", [])),
            "last_checkpoint": index.get("last_checkpoint", ""),
            "session_id": session_id,
        }
    except Exception:
        return {"has_checkpoints": False, "checkpoint_count": 0}
