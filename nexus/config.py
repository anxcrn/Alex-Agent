"""Nexus configuration manager — thread-safe singleton access.

Reads configuration from ``<alex_home>/nexus.yaml``, creating a sensible
default file on first run.  All access goes through ``load_config()`` which
returns a frozen snapshot; mutations go through ``save_config()`` which does
an atomic YAML write.

The module is import-safe (no side effects at import time) and fully
thread-safe for concurrent reads and writes.
"""

from __future__ import annotations

import copy
import logging
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from alex_constants import get_alex_home

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SafetyConfig:
    """Safety guardrails for autonomous evolution.

    Every safety lever defaults to the safest option (enabled/on).
    """
    require_sandbox: bool = True
    security_scan: bool = True
    backup_before_modify: bool = True
    kill_switch: bool = False


@dataclass
class SourcesConfig:
    """Which discovery sources are enabled for crawling.

    Sources default to ``False`` — the operator explicitly opts in to each
    source.  This prevents surprise network traffic on first start.
    """
    github: bool = False
    mcp_registries: bool = False
    pypi: bool = False
    npm: bool = False
    reddit: bool = False
    hackernews: bool = False
    youtube: bool = False
    arxiv: bool = False
    web: bool = False
    docs: bool = False


@dataclass
class CrawlerConfig:
    """Fine-grained crawler knobs."""
    github_stars_threshold: int = 100
    max_pages_per_scan: int = 20
    youtube_channels: List[str] = field(default_factory=list)


@dataclass
class NexusConfig:
    """Top-level Nexus configuration.

    Attributes:
        enabled:                  Master switch — Nexus does nothing when False.
        mode:                     Autonomy level:
                                    * ``full_auto``  — discover, build, verify, merge
                                    * ``semi_auto``  — discover + build, prompt before merge
                                    * ``cautious``   — discover only, prompt before build
        scan_interval_minutes:    How often the periodic scan runs.
        max_evolutions_per_day:   Hard cap on autonomous changes in a 24h window.
        safety:                   Safety guardrails sub-config.
        sources:                  Enabled discovery sources.
        crawlers:                 Crawler-specific tuning.
    """
    enabled: bool = False
    mode: str = "full_auto"
    scan_interval_minutes: int = 30
    max_evolutions_per_day: int = 50
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    crawlers: CrawlerConfig = field(default_factory=CrawlerConfig)

    def __post_init__(self) -> None:
        valid_modes = {"full_auto", "semi_auto", "cautious"}
        if self.mode not in valid_modes:
            logger.warning(
                "[Nexus] Invalid mode %r — falling back to 'cautious'. "
                "Valid modes: %s",
                self.mode, ", ".join(sorted(valid_modes)),
            )
            self.mode = "cautious"
        if self.scan_interval_minutes < 1:
            logger.warning("[Nexus] scan_interval_minutes=%d < 1; clamping to 1",
                           self.scan_interval_minutes)
            self.scan_interval_minutes = 1
        if self.max_evolutions_per_day < 0:
            self.max_evolutions_per_day = 0


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    """Return the canonical path to ``nexus.yaml``."""
    return get_alex_home() / "nexus.yaml"


# ---------------------------------------------------------------------------
# YAML helpers — try ruamel.yaml first (round-trip safe, preserves comments),
# fall back to PyYAML, then to a manual write as last resort.
# ---------------------------------------------------------------------------

def _yaml_load(text: str) -> Dict[str, Any]:
    """Parse YAML text into a dict, trying available libraries."""
    try:
        from ruamel.yaml import YAML  # type: ignore[import-untyped]
        import io
        yaml = YAML()
        yaml.preserve_quotes = True
        data = yaml.load(io.StringIO(text))
        return dict(data) if data else {}
    except ImportError:
        pass

    try:
        import yaml  # type: ignore[import-untyped]
        data = yaml.safe_load(text)
        return dict(data) if data else {}
    except ImportError:
        pass

    # Absolute last resort — should never happen in practice
    raise ImportError(
        "Neither ruamel.yaml nor PyYAML is installed.  Install one of them: "
        "pip install ruamel.yaml   OR   pip install pyyaml"
    )


def _yaml_dump(data: Dict[str, Any]) -> str:
    """Serialize a dict to a YAML string."""
    try:
        from ruamel.yaml import YAML  # type: ignore[import-untyped]
        import io
        yaml = YAML()
        yaml.default_flow_style = False
        stream = io.StringIO()
        yaml.dump(data, stream)
        return stream.getvalue()
    except ImportError:
        pass

    try:
        import yaml  # type: ignore[import-untyped]
        return yaml.dump(data, default_flow_style=False, sort_keys=False)
    except ImportError:
        pass

    raise ImportError("No YAML library available.")


# ---------------------------------------------------------------------------
# De/serialization
# ---------------------------------------------------------------------------

def _dict_to_config(raw: Dict[str, Any]) -> NexusConfig:
    """Build a NexusConfig from a raw dict, ignoring unknown keys gracefully."""
    safety_raw = raw.get("safety") or {}
    sources_raw = raw.get("sources") or {}
    crawlers_raw = raw.get("crawlers") or {}

    # Build sub-configs, only passing known fields
    safety = SafetyConfig(
        require_sandbox=bool(safety_raw.get("require_sandbox", True)),
        security_scan=bool(safety_raw.get("security_scan", True)),
        backup_before_modify=bool(safety_raw.get("backup_before_modify", True)),
        kill_switch=bool(safety_raw.get("kill_switch", False)),
    )
    sources = SourcesConfig(
        github=bool(sources_raw.get("github", False)),
        mcp_registries=bool(sources_raw.get("mcp_registries", False)),
        pypi=bool(sources_raw.get("pypi", False)),
        npm=bool(sources_raw.get("npm", False)),
        reddit=bool(sources_raw.get("reddit", False)),
        hackernews=bool(sources_raw.get("hackernews", False)),
        youtube=bool(sources_raw.get("youtube", False)),
        arxiv=bool(sources_raw.get("arxiv", False)),
        web=bool(sources_raw.get("web", False)),
        docs=bool(sources_raw.get("docs", False)),
    )
    yt_channels = crawlers_raw.get("youtube_channels")
    if not isinstance(yt_channels, list):
        yt_channels = []
    crawlers = CrawlerConfig(
        github_stars_threshold=int(crawlers_raw.get("github_stars_threshold", 100)),
        max_pages_per_scan=int(crawlers_raw.get("max_pages_per_scan", 20)),
        youtube_channels=[str(c) for c in yt_channels],
    )

    return NexusConfig(
        enabled=bool(raw.get("enabled", False)),
        mode=str(raw.get("mode", "full_auto")),
        scan_interval_minutes=int(raw.get("scan_interval_minutes", 30)),
        max_evolutions_per_day=int(raw.get("max_evolutions_per_day", 50)),
        safety=safety,
        sources=sources,
        crawlers=crawlers,
    )


def _config_to_dict(cfg: NexusConfig) -> Dict[str, Any]:
    """Convert a NexusConfig to a plain dict suitable for YAML serialization."""
    return asdict(cfg)


# ---------------------------------------------------------------------------
# Default file content
# ---------------------------------------------------------------------------

_DEFAULT_YAML_HEADER = """\
# ──────────────────────────────────────────────────────────────────────
# Nexus — Self-Evolution Engine Configuration
# ──────────────────────────────────────────────────────────────────────
# This file controls the Nexus autonomous discovery-and-evolution system.
# Edit this file or use `alex nexus config` to change settings.
#
# Modes:
#   full_auto  — Nexus discovers, builds, verifies, and merges autonomously.
#   semi_auto  — Nexus discovers and builds; prompts you before merging.
#   cautious   — Nexus discovers only; prompts you before building anything.
# ──────────────────────────────────────────────────────────────────────

"""


def _write_default_config(path: Path) -> NexusConfig:
    """Create the default nexus.yaml file and return the config."""
    cfg = NexusConfig()
    body = _yaml_dump(_config_to_dict(cfg))
    content = _DEFAULT_YAML_HEADER + body

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Atomic write: write to temp file then rename
        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent), prefix=".nexus-cfg-", suffix=".yaml",
        )
        try:
            os.write(fd, content.encode("utf-8"))
        finally:
            os.close(fd)

        tmp_path = Path(tmp)
        tmp_path.replace(path)
        logger.info("[Nexus] Created default configuration at %s", path)
    except OSError as exc:
        logger.error("[Nexus] Failed to write default config to %s: %s", path, exc)
        # Clean up the temp file on failure
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass

    return cfg


# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------

_lock = threading.RLock()
_cached_config: Optional[NexusConfig] = None
_cached_mtime: float = 0.0


def load_config(*, force_reload: bool = False) -> NexusConfig:
    """Load (and cache) the Nexus configuration.

    Returns a deep-copied snapshot so callers can read fields without
    holding a lock.  The file is re-read only when its mtime changes or
    *force_reload* is True.

    Thread-safe.  On parse error the previous valid config is kept; on
    first-run parse error a default config is returned.

    Args:
        force_reload: Ignore the mtime cache and re-read the file.

    Returns:
        A NexusConfig snapshot.
    """
    global _cached_config, _cached_mtime

    path = _config_path()

    with _lock:
        # Fast path: return cached config if file hasn't changed
        if not force_reload and _cached_config is not None:
            try:
                current_mtime = path.stat().st_mtime
                if current_mtime == _cached_mtime:
                    return copy.deepcopy(_cached_config)
            except OSError:
                # File was deleted — return cached copy
                return copy.deepcopy(_cached_config)

        # File doesn't exist — create defaults
        if not path.exists():
            _cached_config = _write_default_config(path)
            try:
                _cached_mtime = path.stat().st_mtime
            except OSError:
                _cached_mtime = 0.0
            return copy.deepcopy(_cached_config)

        # Read and parse
        try:
            text = path.read_text(encoding="utf-8")
            raw = _yaml_load(text)
            config = _dict_to_config(raw)
            _cached_config = config
            _cached_mtime = path.stat().st_mtime
            logger.debug("[Nexus] Configuration loaded from %s", path)
            return copy.deepcopy(config)
        except Exception as exc:
            logger.error(
                "[Nexus] Failed to parse %s: %s — using previous/default config",
                path, exc,
            )
            if _cached_config is not None:
                return copy.deepcopy(_cached_config)
            _cached_config = NexusConfig()
            return copy.deepcopy(_cached_config)


def save_config(cfg: NexusConfig) -> None:
    """Persist a NexusConfig to disk.

    Performs an atomic write (temp file → rename) so readers never see a
    partially-written file.

    Thread-safe.

    Args:
        cfg: The configuration to write.
    """
    global _cached_config, _cached_mtime

    path = _config_path()
    data = _config_to_dict(cfg)
    body = _yaml_dump(data)
    content = _DEFAULT_YAML_HEADER + body

    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path_str: Optional[str] = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(path.parent), prefix=".nexus-cfg-", suffix=".yaml",
            )
            try:
                os.write(fd, content.encode("utf-8"))
            finally:
                os.close(fd)

            Path(tmp_path_str).replace(path)
            _cached_config = copy.deepcopy(cfg)
            try:
                _cached_mtime = path.stat().st_mtime
            except OSError:
                _cached_mtime = 0.0
            logger.info("[Nexus] Configuration saved to %s", path)
        except OSError as exc:
            logger.error("[Nexus] Failed to save config to %s: %s", path, exc)
            # Clean up temp on failure
            if tmp_path_str:
                try:
                    Path(tmp_path_str).unlink(missing_ok=True)
                except Exception:
                    pass
            raise


def invalidate_cache() -> None:
    """Force the next ``load_config()`` call to re-read the file.

    Useful after an external tool has modified nexus.yaml directly.
    """
    global _cached_config, _cached_mtime
    with _lock:
        _cached_config = None
        _cached_mtime = 0.0
