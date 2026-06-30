"""Nexus changelog — immutable, append-only evolution audit trail.

Every action taken by the Nexus self-evolution engine is recorded here:
discoveries, analyses, builds, verifications, merges, and rollbacks.

Storage format is ``.jsonl`` (JSON Lines) — one JSON object per line —
which is naturally append-friendly and survives partial writes (the
worst case is a truncated last line, easily detected).

The file lives at ``<alex_home>/nexus/changelog.jsonl``.

Thread-safe.  Uses both an in-process ``threading.RLock`` and a
cross-process advisory file lock so concurrent gateway processes,
CLI invocations, and the background Nexus daemon all serialize
correctly.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from alex_constants import get_alex_home

logger = logging.getLogger(__name__)

# Cross-platform file locking — same approach as cron/jobs.py
try:
    import fcntl  # type: ignore[import-not-found]
except ImportError:
    fcntl = None  # type: ignore[assignment]
try:
    import msvcrt  # type: ignore[import-not-found]
except ImportError:
    msvcrt = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Valid action verbs for changelog entries.
VALID_ACTIONS = frozenset({
    "discovered",
    "analyzed",
    "built",
    "verified",
    "merged",
    "rolled_back",
})

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ChangelogEntry:
    """A single, immutable record in the Nexus evolution changelog.

    Attributes:
        id:                   Unique identifier (UUID4).
        timestamp:            ISO-8601 UTC timestamp of when the entry was created.
        action:               The action type — one of ``VALID_ACTIONS``.
        source_url:           URL of the source that triggered this entry.
        source_type:          Kind of source (``github``, ``mcp_registry``, …).
        description:          Human-readable description of what happened.
        file_path:            Path to the file that was created / modified, if any.
        diff:                 Unified diff of the change, if applicable.
        verification_result:  ``pass`` or ``fail`` if the change was verified.
        confidence_score:     0–100 confidence metric for the change.
        rollback_token:       Opaque token that can be used to reverse the change.
        metadata:             Arbitrary extra data for downstream consumers.
    """
    id: str = ""
    timestamp: str = ""
    action: str = ""
    source_url: str = ""
    source_type: str = ""
    description: str = ""
    file_path: Optional[str] = None
    diff: Optional[str] = None
    verification_result: Optional[str] = None
    confidence_score: Optional[float] = None
    rollback_token: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.confidence_score is not None:
            self.confidence_score = max(0.0, min(100.0, float(self.confidence_score)))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (JSON-safe)."""
        return asdict(self)

    def to_json_line(self) -> str:
        """Serialize to a single JSON line (no trailing newline)."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangelogEntry":
        """Construct a ChangelogEntry from a dict, ignoring unknown keys."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class Changelog:
    """Class wrapper for the append-only changelog file."""

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._path = Path(file_path) if file_path is not None else _changelog_path()

    def append(self, **kwargs) -> ChangelogEntry:
        # Check if the user passed an entry object, or passed keyword arguments
        entry = kwargs.get("entry")
        if isinstance(entry, ChangelogEntry):
            pass
        else:
            entry = ChangelogEntry(
                action=kwargs.get("action", ""),
                source_url=kwargs.get("source_url", ""),
                source_type=kwargs.get("source_type", ""),
                description=kwargs.get("description", ""),
                file_path=kwargs.get("file_path"),
                diff=kwargs.get("diff"),
                verification_result=kwargs.get("verification_result"),
                confidence_score=kwargs.get("confidence_score"),
                rollback_token=kwargs.get("rollback_token"),
                metadata=kwargs.get("metadata")
            )
            
        if entry.action and entry.action not in VALID_ACTIONS:
            logger.warning(
                "[Nexus/Changelog] Unknown action %r — recording anyway. "
                "Known actions: %s", entry.action, ", ".join(sorted(VALID_ACTIONS)),
            )

        line = entry.to_json_line() + "\n"

        with _changelog_lock():
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
                logger.debug(
                    "[Nexus/Changelog] Appended entry %s action=%s",
                    entry.id, entry.action,
                )
            except OSError as exc:
                logger.error(
                    "[Nexus/Changelog] Failed to append entry %s: %s", entry.id, exc,
                )

        return entry

    def get_entries(
        self,
        *,
        action: Optional[str] = None,
        source_type: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        file_path: Optional[str] = None,
        predicate: Optional[Callable[[ChangelogEntry], bool]] = None,
    ) -> List[ChangelogEntry]:
        path = self._path
        entries: List[ChangelogEntry] = []

        with _changelog_lock():
            if not path.exists():
                return entries

            try:
                with open(path, "r", encoding="utf-8") as fh:
                    for line_no, raw_line in enumerate(fh, start=1):
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        try:
                            data = json.loads(raw_line)
                            entry = ChangelogEntry.from_dict(data)
                        except (json.JSONDecodeError, TypeError, ValueError) as exc:
                            logger.warning(
                                "[Nexus/Changelog] Skipping malformed line %d: %s",
                                line_no, exc,
                            )
                            continue

                        # Apply filters
                        if action and entry.action != action:
                            continue
                        if source_type and entry.source_type != source_type:
                            continue
                        if since and entry.timestamp < since:
                            continue
                        if until and entry.timestamp > until:
                            continue
                        if file_path and entry.file_path != file_path:
                            continue
                        if predicate and not predicate(entry):
                            continue

                        entries.append(entry)
            except OSError as exc:
                logger.error("[Nexus/Changelog] Failed to read %s: %s", path, exc)

        return entries

    def get_recent(self, n: int = 10) -> List[ChangelogEntry]:
        n = max(1, n)
        path = self._path

        with _changelog_lock():
            if not path.exists():
                return []

            try:
                file_size = path.stat().st_size
            except OSError:
                return []

            if file_size < 256 * 1024:
                all_entries = self.get_entries()
                return list(reversed(all_entries[-n:]))

            all_entries = self.get_entries()
            return list(reversed(all_entries[-n:]))

    def generate_summary(self, n: int = 20) -> str:
        entries = self.get_recent(n)
        if not entries:
            return "No evolution history recorded yet."
        summary = ["### 🧬 Alex Agent Evolution Changelog", ""]
        for entry in entries:
            summary.append(f"- [{entry.timestamp[:19]}] **{entry.action.upper()}**: {entry.description}")
        return "\n".join(summary)

    def entry_count(self) -> int:
        return len(self.get_entries())

    def clear(self, *, confirm: bool = False) -> bool:
        if not confirm:
            return False
        with _changelog_lock():
            if self._path.exists():
                self._path.unlink()
            return True


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _changelog_dir() -> Path:
    """Return the nexus data directory."""
    return get_alex_home() / "nexus"


def _changelog_path() -> Path:
    """Return the canonical path to the changelog file."""
    return _changelog_dir() / "changelog.jsonl"


def _lock_path() -> Path:
    """Return the advisory-lock file path."""
    return _changelog_dir() / ".changelog.lock"


def _ensure_dir() -> None:
    """Create the nexus directory if it doesn't exist."""
    _changelog_dir().mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

_thread_lock = threading.RLock()
_lock_depth = threading.local()


@contextlib.contextmanager
def _changelog_lock():
    """Serialize changelog operations.

    Combines an in-process ``RLock`` with a cross-process advisory file
    lock.  Re-entrant within the same thread (nested calls reuse the
    held lock).  Degrades gracefully to in-process-only if file locking
    is unavailable.
    """
    depth = getattr(_lock_depth, "depth", 0)
    if depth:
        _lock_depth.depth = depth + 1
        try:
            yield
        finally:
            _lock_depth.depth -= 1
        return

    with _thread_lock:
        _lock_depth.depth = 1
        lock_fd = None
        try:
            try:
                _ensure_dir()
                lock_fd = open(_lock_path(), "a+", encoding="utf-8")
                lock_fd.seek(0)
                if fcntl is not None:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                elif msvcrt is not None:
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
            except (OSError, IOError) as exc:
                logger.warning(
                    "[Nexus/Changelog] Cross-process lock unavailable (%s); "
                    "using in-process lock only", exc,
                )
            try:
                yield
            finally:
                if lock_fd is not None:
                    try:
                        if fcntl is not None:
                            fcntl.flock(lock_fd, fcntl.LOCK_UN)
                        elif msvcrt is not None:
                            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
                    except (OSError, IOError):
                        pass
                    finally:
                        lock_fd.close()
        finally:
            _lock_depth.depth = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def append(entry: ChangelogEntry) -> ChangelogEntry:
    """Append a changelog entry atomically.

    The entry is validated, serialized to a single JSON line, and
    appended to the changelog file under the cross-process lock.  On
    I/O failure the error is logged but not raised — the caller's
    pipeline should not abort because the audit log hiccuped.

    Args:
        entry: The ChangelogEntry to persist.

    Returns:
        The (potentially auto-populated) entry that was written.
    """
    if entry.action and entry.action not in VALID_ACTIONS:
        logger.warning(
            "[Nexus/Changelog] Unknown action %r — recording anyway. "
            "Known actions: %s", entry.action, ", ".join(sorted(VALID_ACTIONS)),
        )

    line = entry.to_json_line() + "\n"

    with _changelog_lock():
        try:
            _ensure_dir()
            path = _changelog_path()
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            logger.debug(
                "[Nexus/Changelog] Appended entry %s action=%s",
                entry.id, entry.action,
            )
        except OSError as exc:
            logger.error(
                "[Nexus/Changelog] Failed to append entry %s: %s", entry.id, exc,
            )

    return entry


def get_entries(
    *,
    action: Optional[str] = None,
    source_type: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    file_path: Optional[str] = None,
    predicate: Optional[Callable[[ChangelogEntry], bool]] = None,
) -> List[ChangelogEntry]:
    """Read changelog entries, optionally filtered.

    All filter parameters are ANDed — an entry must match every
    specified filter to be included.

    Args:
        action:       Filter by action verb (e.g. ``"merged"``).
        source_type:  Filter by source type (e.g. ``"github"``).
        since:        ISO-8601 lower bound (inclusive) on timestamp.
        until:        ISO-8601 upper bound (inclusive) on timestamp.
        file_path:    Filter to entries that modified a specific file path.
        predicate:    Arbitrary callable filter.

    Returns:
        List of matching entries in chronological order (oldest first).
    """
    path = _changelog_path()
    entries: List[ChangelogEntry] = []

    with _changelog_lock():
        if not path.exists():
            return entries

        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line_no, raw_line in enumerate(fh, start=1):
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        data = json.loads(raw_line)
                        entry = ChangelogEntry.from_dict(data)
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        logger.warning(
                            "[Nexus/Changelog] Skipping malformed line %d: %s",
                            line_no, exc,
                        )
                        continue

                    # Apply filters
                    if action and entry.action != action:
                        continue
                    if source_type and entry.source_type != source_type:
                        continue
                    if since and entry.timestamp < since:
                        continue
                    if until and entry.timestamp > until:
                        continue
                    if file_path and entry.file_path != file_path:
                        continue
                    if predicate and not predicate(entry):
                        continue

                    entries.append(entry)
        except OSError as exc:
            logger.error("[Nexus/Changelog] Failed to read %s: %s", path, exc)

    return entries


def get_recent(n: int = 10) -> List[ChangelogEntry]:
    """Return the *n* most recent changelog entries.

    Optimized for the common case: reads the file tail without loading
    the entire history into memory for very large files.  Falls back to
    a full scan for small files or on seek errors.

    Args:
        n: Number of entries to return. Clamped to >= 1.

    Returns:
        Up to *n* entries, newest first.
    """
    n = max(1, n)
    path = _changelog_path()

    with _changelog_lock():
        if not path.exists():
            return []

        try:
            file_size = path.stat().st_size
        except OSError:
            return []

        # For small files (< 256 KB) just read the whole thing
        if file_size < 256 * 1024:
            all_entries = get_entries()
            return list(reversed(all_entries[-n:]))

        # For larger files, read from the tail
        try:
            lines: List[str] = []
            chunk_size = max(4096, n * 512)  # rough estimate per entry
            with open(path, "rb") as fh:
                # Start from end and read backwards in chunks
                pos = file_size
                remaining_text = b""
                while pos > 0 and len(lines) < n + 1:
                    read_size = min(chunk_size, pos)
                    pos -= read_size
                    fh.seek(pos)
                    chunk = fh.read(read_size) + remaining_text
                    remaining_text = b""

                    decoded = chunk.decode("utf-8", errors="replace")
                    split = decoded.split("\n")
                    # First element may be partial — save for next iteration
                    remaining_text = split[0].encode("utf-8")
                    lines = [l for l in split[1:] if l.strip()] + lines

                # Don't forget the remaining text from the last chunk
                if remaining_text.strip():
                    lines = [remaining_text.decode("utf-8", errors="replace")] + lines

            # Parse the last n lines
            result: List[ChangelogEntry] = []
            for raw_line in lines[-n:]:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                    result.append(ChangelogEntry.from_dict(data))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

            return list(reversed(result))

        except (OSError, UnicodeDecodeError) as exc:
            logger.warning(
                "[Nexus/Changelog] Tail-read failed (%s); falling back to full scan",
                exc,
            )
            all_entries = get_entries()
            return list(reversed(all_entries[-n:]))


def generate_summary(n: int = 20) -> str:
    """Generate a human-readable summary of recent changelog activity.

    Groups entries by action type and provides counts and highlights.

    Args:
        n: How many recent entries to summarize.

    Returns:
        A formatted multi-line string.
    """
    entries = get_recent(n)
    if not entries:
        return "Nexus Changelog: No activity recorded yet."

    # Compute date range
    timestamps = [e.timestamp for e in entries if e.timestamp]
    if timestamps:
        newest = timestamps[0][:19]  # trim to seconds
        oldest = timestamps[-1][:19]
    else:
        newest = oldest = "unknown"

    # Group by action
    by_action: Dict[str, List[ChangelogEntry]] = {}
    for entry in entries:
        by_action.setdefault(entry.action or "unknown", []).append(entry)

    lines = [
        f"═══ Nexus Activity Summary ({len(entries)} entries) ═══",
        f"  Period: {oldest} → {newest}",
        "",
    ]

    # Ordered presentation
    action_order = ["discovered", "analyzed", "built", "verified", "merged", "rolled_back"]
    action_labels = {
        "discovered": "🔍 Discovered",
        "analyzed": "🧪 Analyzed",
        "built": "🔨 Built",
        "verified": "✅ Verified",
        "merged": "🚀 Merged",
        "rolled_back": "⏪ Rolled Back",
    }

    for action in action_order:
        group = by_action.pop(action, [])
        if not group:
            continue
        label = action_labels.get(action, action.title())
        lines.append(f"  {label}: {len(group)}")
        # Show up to 3 highlights per group
        for entry in group[:3]:
            source_tag = f"[{entry.source_type}]" if entry.source_type else ""
            desc = entry.description[:80] if entry.description else entry.source_url[:80]
            confidence = ""
            if entry.confidence_score is not None:
                confidence = f" ({entry.confidence_score:.0f}%)"
            lines.append(f"    • {source_tag} {desc}{confidence}")
        if len(group) > 3:
            lines.append(f"    … and {len(group) - 3} more")
        lines.append("")

    # Any remaining unknown actions
    for action, group in by_action.items():
        lines.append(f"  {action}: {len(group)}")
        lines.append("")

    # Verification stats
    verified = [e for e in entries if e.verification_result]
    if verified:
        passed = sum(1 for e in verified if e.verification_result == "pass")
        failed = sum(1 for e in verified if e.verification_result == "fail")
        lines.append(f"  Verification: {passed} passed, {failed} failed")

    # Average confidence
    scored = [e.confidence_score for e in entries if e.confidence_score is not None]
    if scored:
        avg = sum(scored) / len(scored)
        lines.append(f"  Average confidence: {avg:.1f}%")

    return "\n".join(lines)


def entry_count() -> int:
    """Return the total number of changelog entries without loading them all.

    Counts non-empty lines in the JSONL file.
    """
    path = _changelog_path()
    if not path.exists():
        return 0

    count = 0
    with _changelog_lock():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        count += 1
        except OSError as exc:
            logger.error("[Nexus/Changelog] Failed to count entries: %s", exc)
    return count


def clear(*, confirm: bool = False) -> bool:
    """Delete all changelog entries.

    This is a destructive operation.  Requires ``confirm=True`` to
    prevent accidental invocation.

    Args:
        confirm: Must be True to proceed.

    Returns:
        True if the file was cleared, False otherwise.
    """
    if not confirm:
        logger.warning("[Nexus/Changelog] clear() called without confirm=True — refusing.")
        return False

    path = _changelog_path()
    with _changelog_lock():
        try:
            if path.exists():
                # Atomic truncation: write empty temp then replace
                fd, tmp = tempfile.mkstemp(
                    dir=str(path.parent), prefix=".changelog-", suffix=".jsonl",
                )
                os.close(fd)
                Path(tmp).replace(path)
                logger.info("[Nexus/Changelog] Changelog cleared.")
            return True
        except OSError as exc:
            logger.error("[Nexus/Changelog] Failed to clear changelog: %s", exc)
            return False
