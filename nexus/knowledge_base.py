"""SQLite knowledge store for Project Nexus.

Provides persistent storage for discoveries, extracted knowledge,
discovered MCP servers, and evolution audit logs.  Uses WAL mode for
concurrent readers and a connection-per-thread pattern for thread safety.

Database location: ``get_alex_home() / 'nexus' / 'knowledge.db'``
"""

import hashlib
import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alex_constants import get_alex_home

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS discoveries (
    id            TEXT PRIMARY KEY,
    source_type   TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    title         TEXT NOT NULL,
    content       TEXT NOT NULL,
    content_hash  TEXT UNIQUE NOT NULL,
    category      TEXT NOT NULL DEFAULT 'unknown',
    relevance_score REAL NOT NULL DEFAULT 0.0,
    status        TEXT NOT NULL DEFAULT 'new',
    discovered_at TEXT NOT NULL,
    metadata      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS knowledge (
    id            TEXT PRIMARY KEY,
    discovery_id  TEXT NOT NULL REFERENCES discoveries(id),
    summary       TEXT NOT NULL,
    code_snippet  TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT 'technique',
    actionable    BOOLEAN NOT NULL DEFAULT 0,
    extracted_at  TEXT NOT NULL,
    metadata      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS mcps_discovered (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    registry_source TEXT NOT NULL DEFAULT '',
    install_command TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'discovered',
    discovered_at   TEXT NOT NULL,
    config          TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS evolution_log (
    id            TEXT PRIMARY KEY,
    changelog_id  TEXT NOT NULL DEFAULT '',
    file_path     TEXT NOT NULL DEFAULT '',
    action        TEXT NOT NULL DEFAULT 'create',
    backup_path   TEXT NOT NULL DEFAULT '',
    diff          TEXT NOT NULL DEFAULT '',
    verified      BOOLEAN NOT NULL DEFAULT 0,
    merged_at     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_discoveries_status ON discoveries(status);
CREATE INDEX IF NOT EXISTS idx_discoveries_category ON discoveries(category);
CREATE INDEX IF NOT EXISTS idx_discoveries_discovered_at ON discoveries(discovered_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_discovery_id ON knowledge(discovery_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category);
CREATE INDEX IF NOT EXISTS idx_mcps_status ON mcps_discovered(status);
CREATE INDEX IF NOT EXISTS idx_evolution_changelog ON evolution_log(changelog_id);
"""

_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS discoveries_fts USING fts5(
    title, content, content='discoveries', content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    summary, code_snippet, content='knowledge', content_rowid='rowid'
);
"""

# Triggers that keep the FTS indexes in sync with the content tables.
_FTS_TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS discoveries_ai AFTER INSERT ON discoveries BEGIN
    INSERT INTO discoveries_fts(rowid, title, content)
    VALUES (new.rowid, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS discoveries_ad AFTER DELETE ON discoveries BEGIN
    INSERT INTO discoveries_fts(discoveries_fts, rowid, title, content)
    VALUES ('delete', old.rowid, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS discoveries_au AFTER UPDATE ON discoveries BEGIN
    INSERT INTO discoveries_fts(discoveries_fts, rowid, title, content)
    VALUES ('delete', old.rowid, old.title, old.content);
    INSERT INTO discoveries_fts(rowid, title, content)
    VALUES (new.rowid, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
    INSERT INTO knowledge_fts(rowid, summary, code_snippet)
    VALUES (new.rowid, new.summary, new.code_snippet);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, summary, code_snippet)
    VALUES ('delete', old.rowid, old.summary, old.code_snippet);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, summary, code_snippet)
    VALUES ('delete', old.rowid, old.summary, old.code_snippet);
    INSERT INTO knowledge_fts(rowid, summary, code_snippet)
    VALUES (new.rowid, new.summary, new.code_snippet);
END;
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def compute_content_hash(text: str) -> str:
    """Compute a SHA-256 hex digest used for deduplication."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _new_id() -> str:
    """Generate a short, unique identifier."""
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """Thread-safe SQLite knowledge store for Nexus.

    Each thread gets its own ``sqlite3.Connection`` via a ``threading.local``
    instance.  The database runs in WAL mode so readers never block writers
    and vice versa.

    Usage::

        kb = KnowledgeBase()
        kb.add_discovery(source_type="github", source_url="...", ...)
        results = kb.search_discoveries("async MCP server")
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize the knowledge base.

        Args:
            db_path: Override path for the database file.  Defaults to
                ``get_alex_home() / 'nexus' / 'knowledge.db'``.
        """
        if db_path is None:
            db_path = get_alex_home() / "nexus" / "knowledge.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._schema_ready = False
        logger.debug("[Nexus/KB] Database path: %s", self._db_path)

    # -- connection helpers -------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return a per-thread connection, creating it if needed."""
        conn: Optional[sqlite3.Connection] = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self._db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")
            self._local.conn = conn
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create tables and FTS indexes on first access (idempotent)."""
        if self._schema_ready:
            return
        with self._init_lock:
            if self._schema_ready:
                return
            try:
                conn.executescript(_SCHEMA_SQL)
                conn.executescript(_FTS_SQL)
                conn.executescript(_FTS_TRIGGERS_SQL)
                conn.commit()
                self._schema_ready = True
                logger.debug("[Nexus/KB] Schema initialized successfully")
            except sqlite3.Error as exc:
                logger.error("[Nexus/KB] Schema creation failed: %s", exc)
                raise

    # -----------------------------------------------------------------------
    # Discoveries
    # -----------------------------------------------------------------------

    def add_discovery(
        self,
        source_type: str,
        source_url: str,
        title: str,
        content: str,
        category: str = "unknown",
        relevance_score: float = 0.0,
        status: str = "new",
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
        content_hash: Optional[str] = None,
    ) -> Optional[str]:
        """Insert a new discovery, returning its id or None on duplicate.

        Content is hashed for deduplication — if the same hash already exists
        the row is silently skipped.

        Args:
            source_type: Origin of the discovery (e.g. ``'github'``).
            source_url: URL or reference to the source.
            title: Short title / headline.
            content: Full text body.
            category: Category label (e.g. ``'skill'``, ``'mcp_server'``).
            relevance_score: Computed relevance 0.0–1.0.
            status: Lifecycle status (``'new'``, ``'analyzed'``, etc.).
            metadata: Arbitrary JSON-safe dict.
            id: Optional custom pre-computed ID.
            content_hash: Optional custom pre-computed content hash.

        Returns:
            The generated id string, or ``None`` if the hash was a duplicate.
        """
        conn = self._get_conn()
        disc_id = id if id is not None else _new_id()
        c_hash = content_hash if content_hash is not None else compute_content_hash(f"{source_url}|{title}|{content[:2000]}")
        meta_json = json.dumps(metadata or {}, default=str)
        try:
            conn.execute(
                """INSERT INTO discoveries
                   (id, source_type, source_url, title, content, content_hash,
                    category, relevance_score, status, discovered_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (disc_id, source_type, source_url, title, content, c_hash,
                 category, relevance_score, status, _now_iso(), meta_json),
            )
            conn.commit()
            logger.debug("[Nexus/KB] Added discovery %s: %s", disc_id, title[:60])
            return disc_id
        except sqlite3.IntegrityError:
            logger.debug("[Nexus/KB] Duplicate content hash, skipping: %s", title[:60])
            return None
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] Failed to add discovery: %s", exc)
            return None

    def get_discovery(self, discovery_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single discovery by id.

        Args:
            discovery_id: The primary key of the discovery.

        Returns:
            A dict with all columns, or ``None`` if not found.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM discoveries WHERE id = ?", (discovery_id,)
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] get_discovery failed: %s", exc)
            return None

    def search_discoveries(
        self,
        query: str,
        limit: int = 20,
        status: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Full-text search over discovery titles and content.

        Args:
            query: The FTS5 search query string.
            limit: Maximum number of results.
            status: Optional filter by status.
            category: Optional filter by category.

        Returns:
            List of matching discovery dicts, ranked by FTS relevance.
        """
        conn = self._get_conn()
        try:
            # Build FTS query, joining back to the main table for filtering
            sql = """
                SELECT d.*
                FROM discoveries d
                JOIN discoveries_fts fts ON d.rowid = fts.rowid
                WHERE discoveries_fts MATCH ?
            """
            params: list[Any] = [query]
            if status:
                sql += " AND d.status = ?"
                params.append(status)
            if category:
                sql += " AND d.category = ?"
                params.append(category)
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] search_discoveries failed: %s", exc)
            return []

    def has_content_hash(self, hash_value: str) -> bool:
        """Check whether a content_hash already exists in discoveries.

        Args:
            hash_value: SHA-256 hex digest.

        Returns:
            ``True`` if the hash exists, ``False`` otherwise.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM discoveries WHERE content_hash = ? LIMIT 1",
                (hash_value,),
            ).fetchone()
            return row is not None
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] has_content_hash failed: %s", exc)
            return False

    def update_discovery_status(self, discovery_id: str, status: str) -> bool:
        """Update the status of a discovery.

        Args:
            discovery_id: The primary key of the discovery.
            status: New status value.

        Returns:
            ``True`` if the row was updated.
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "UPDATE discoveries SET status = ? WHERE id = ?",
                (status, discovery_id),
            )
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] update_discovery_status failed: %s", exc)
            return False

    # -----------------------------------------------------------------------
    # Knowledge
    # -----------------------------------------------------------------------

    def add_knowledge(
        self,
        discovery_id: str,
        summary: str,
        code_snippet: str = "",
        category: str = "technique",
        actionable: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
    ) -> Optional[str]:
        """Insert a knowledge record extracted from a discovery.

        Args:
            discovery_id: FK to the parent discovery.
            summary: Human-readable summary of the knowledge.
            code_snippet: Optional code example.
            category: One of ``skill``, ``tool``, ``mcp_server``,
                ``technique``, ``api``, ``library``.
            actionable: Whether this knowledge can be directly acted on.
            metadata: Arbitrary JSON-safe dict.
            id: Optional custom ID.

        Returns:
            The generated id string, or ``None`` on error.
        """
        conn = self._get_conn()
        k_id = id if id is not None else _new_id()
        meta_json = json.dumps(metadata or {}, default=str)
        try:
            conn.execute(
                """INSERT INTO knowledge
                   (id, discovery_id, summary, code_snippet, category,
                    actionable, extracted_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (k_id, discovery_id, summary, code_snippet, category,
                 int(actionable), _now_iso(), meta_json),
            )
            conn.commit()
            logger.debug("[Nexus/KB] Added knowledge %s from discovery %s", k_id, discovery_id)
            return k_id
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] Failed to add knowledge: %s", exc)
            return None

    def get_knowledge(self, knowledge_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single knowledge record by id.

        Args:
            knowledge_id: The primary key of the knowledge record.

        Returns:
            A dict with all columns, or ``None`` if not found.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM knowledge WHERE id = ?", (knowledge_id,)
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] get_knowledge failed: %s", exc)
            return None

    def search_knowledge(
        self,
        query: str,
        limit: int = 20,
        category: Optional[str] = None,
        actionable_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Full-text search over knowledge summaries and code snippets.

        Args:
            query: The FTS5 search query string.
            limit: Maximum number of results.
            category: Optional filter by category.
            actionable_only: If ``True``, only return actionable records.

        Returns:
            List of matching knowledge dicts.
        """
        conn = self._get_conn()
        try:
            sql = """
                SELECT k.*
                FROM knowledge k
                JOIN knowledge_fts fts ON k.rowid = fts.rowid
                WHERE knowledge_fts MATCH ?
            """
            params: list[Any] = [query]
            if category:
                sql += " AND k.category = ?"
                params.append(category)
            if actionable_only:
                sql += " AND k.actionable = 1"
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] search_knowledge failed: %s", exc)
            return []

    # -----------------------------------------------------------------------
    # MCP Servers Discovered
    # -----------------------------------------------------------------------

    def add_mcp(
        self,
        name: str,
        registry_source: str = "",
        install_command: str = "",
        description: str = "",
        status: str = "discovered",
        config: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
    ) -> Optional[str]:
        """Record a newly discovered MCP server.

        Args:
            name: Human-readable name of the MCP server.
            registry_source: Where it was found (e.g. ``'npm'``, ``.github``).
            install_command: Shell command to install it.
            description: Short description.
            status: One of ``discovered``, ``installed``, ``verified``, ``failed``.
            config: JSON-safe configuration dict.
            id: Optional custom ID.

        Returns:
            The generated id string, or ``None`` on error.
        """
        conn = self._get_conn()
        mcp_id = id if id is not None else _new_id()
        config_json = json.dumps(config or {}, default=str)
        try:
            conn.execute(
                """INSERT INTO mcps_discovered
                   (id, name, registry_source, install_command, description,
                    status, discovered_at, config)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (mcp_id, name, registry_source, install_command, description,
                 status, _now_iso(), config_json),
            )
            conn.commit()
            logger.debug("[Nexus/KB] Added MCP server %s: %s", mcp_id, name)
            return mcp_id
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] Failed to add MCP: %s", exc)
            return None

    def get_mcp(self, mcp_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single MCP server record by id.

        Args:
            mcp_id: The primary key.

        Returns:
            A dict with all columns, or ``None`` if not found.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM mcps_discovered WHERE id = ?", (mcp_id,)
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] get_mcp failed: %s", exc)
            return None

    def list_mcps(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List MCP servers, optionally filtered by status.

        Args:
            status: Optional status filter.
            limit: Maximum rows to return.

        Returns:
            List of MCP dicts ordered by most-recently discovered first.
        """
        conn = self._get_conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM mcps_discovered WHERE status = ? "
                    "ORDER BY discovered_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM mcps_discovered "
                    "ORDER BY discovered_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] list_mcps failed: %s", exc)
            return []

    def update_mcp_status(self, mcp_id: str, status: str) -> bool:
        """Update the status of a discovered MCP server.

        Args:
            mcp_id: The primary key.
            status: New status (``'discovered'``, ``'installed'``,
                ``'verified'``, ``'failed'``).

        Returns:
            ``True`` if the row was updated.
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "UPDATE mcps_discovered SET status = ? WHERE id = ?",
                (status, mcp_id),
            )
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] update_mcp_status failed: %s", exc)
            return False

    # -----------------------------------------------------------------------
    # Evolution Log
    # -----------------------------------------------------------------------

    def add_evolution(
        self,
        changelog_id: str = "",
        file_path: str = "",
        action: str = "create",
        backup_path: str = "",
        diff: str = "",
        verified: bool = False,
        id: Optional[str] = None,
    ) -> Optional[str]:
        """Record an evolution event (file creation/modification/deletion).

        Args:
            changelog_id: FK to the changelog entry that triggered this.
            file_path: Path of the file that was created/modified/deleted.
            action: One of ``'create'``, ``'modify'``, ``'delete'``.
            backup_path: Path to the backup of the original file.
            diff: Unified diff of the change.
            verified: Whether the change passed verification.
            id: Optional custom ID.

        Returns:
            The generated id string, or ``None`` on error.
        """
        conn = self._get_conn()
        evo_id = id if id is not None else _new_id()
        try:
            conn.execute(
                """INSERT INTO evolution_log
                   (id, changelog_id, file_path, action, backup_path,
                    diff, verified, merged_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (evo_id, changelog_id, file_path, action, backup_path,
                 diff, int(verified), _now_iso() if verified else ""),
            )
            conn.commit()
            logger.debug("[Nexus/KB] Added evolution %s: %s %s", evo_id, action, file_path)
            return evo_id
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] Failed to add evolution: %s", exc)
            return None

    def get_evolutions(
        self,
        changelog_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List evolution log entries, optionally filtered by changelog.

        Args:
            changelog_id: Optional FK filter.
            limit: Maximum rows to return.

        Returns:
            List of evolution-log dicts.
        """
        conn = self._get_conn()
        try:
            if changelog_id:
                rows = conn.execute(
                    "SELECT * FROM evolution_log WHERE changelog_id = ? "
                    "ORDER BY merged_at DESC LIMIT ?",
                    (changelog_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM evolution_log ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] get_evolutions failed: %s", exc)
            return []

    # -----------------------------------------------------------------------
    # Statistics & Maintenance
    # -----------------------------------------------------------------------

    def get_stats(self) -> Dict[str, int]:
        """Return row counts for each table.

        Returns:
            Dict mapping table names to their row counts.
        """
        conn = self._get_conn()
        tables = ["discoveries", "knowledge", "mcps_discovered", "evolution_log"]
        stats: Dict[str, int] = {}
        for table in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()  # noqa: S608
                stats[table] = row["cnt"] if row else 0
            except sqlite3.Error:
                stats[table] = -1
        return stats

    def cleanup_old(self, days: int = 90) -> int:
        """Remove old rejected discoveries and their associated knowledge.

        Args:
            days: Remove rejected discoveries older than this many days.

        Returns:
            Number of discovery rows deleted.
        """
        conn = self._get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        try:
            # Delete knowledge rows that reference the about-to-be-deleted discoveries
            conn.execute(
                """DELETE FROM knowledge WHERE discovery_id IN (
                       SELECT id FROM discoveries
                       WHERE status = 'rejected' AND discovered_at < ?
                   )""",
                (cutoff,),
            )
            cur = conn.execute(
                "DELETE FROM discoveries WHERE status = 'rejected' AND discovered_at < ?",
                (cutoff,),
            )
            conn.commit()
            deleted = cur.rowcount
            if deleted:
                logger.info("[Nexus/KB] Cleaned up %d rejected discoveries older than %d days", deleted, days)
            return deleted
        except sqlite3.Error as exc:
            logger.error("[Nexus/KB] cleanup_old failed: %s", exc)
            return 0

    def close(self) -> None:
        """Close the current thread's database connection (if open)."""
        conn: Optional[sqlite3.Connection] = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            self._local.conn = None
