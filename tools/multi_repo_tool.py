"""Multi-repo orchestration tool — coordinate work across multiple repositories.

Allows the agent to clone, inspect, search, and modify multiple git repos
in a single conversation. Ideal for cross-repo refactors, API changes,
and dependency updates.

Tools registered: ``repo_clone``, ``repo_status``, ``repo_search``,
``repo_exec``, ``repo_list``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tools.registry import registry

logger = logging.getLogger(__name__)

_REPOS_DIR_NAME = "repos"


def _get_repos_dir() -> Path:
    """Get the root directory where repos are stored."""
    from alex_constants import get_alex_home
    repos_dir = Path(get_alex_home()) / _REPOS_DIR_NAME
    repos_dir.mkdir(parents=True, exist_ok=True)
    return repos_dir


def _sanitize_repo_name(url_or_name: str) -> str:
    """Convert a git URL to a safe directory name."""
    name = url_or_name.strip().rstrip("/").rstrip(".git")
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", "."))
    return safe or "repo"


def repo_clone(url: str, path: str = "", branch: str = "", depth: int = 0) -> str:
    """Clone a git repository into the workspace.

    Args:
        url: Git remote URL (https, ssh, or local path).
        path: Optional subdirectory name (default: derived from URL).
        branch: Optional branch/tag to checkout.
        depth: Shallow clone depth (0 = full clone).
    """
    try:
        repos_dir = _get_repos_dir()
        target_name = path or _sanitize_repo_name(url)
        target_path = repos_dir / target_name

        if target_path.exists():
            return json.dumps({
                "success": True,
                "name": target_name,
                "path": str(target_path),
                "message": f"Already cloned at {target_path}",
            })

        cmd = ["git", "clone"]
        if depth > 0:
            cmd.extend(["--depth", str(depth)])
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([url, str(target_path)])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return json.dumps({
                "success": False,
                "error": f"Clone failed: {result.stderr.strip()}",
            })

        return json.dumps({
            "success": True,
            "name": target_name,
            "path": str(target_path),
            "message": f"Cloned {url} to {target_path}",
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "Clone timed out (300s)"})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


def repo_status(name: str = "") -> str:
    """Show git status for cloned repos.

    Args:
        name: Specific repo name (empty = all repos).
    """
    try:
        repos_dir = _get_repos_dir()
        results: list[dict[str, Any]] = []

        targets = [repos_dir / name] if name else sorted(repos_dir.iterdir())
        for target in targets:
            if not target.is_dir() or not (target / ".git").exists():
                continue
            try:
                branch = subprocess.run(
                    ["git", "-C", str(target), "branch", "--show-current"],
                    capture_output=True, text=True, timeout=10,
                ).stdout.strip()
                status = subprocess.run(
                    ["git", "-C", str(target), "status", "--porcelain"],
                    capture_output=True, text=True, timeout=10,
                ).stdout.strip()
                log = subprocess.run(
                    ["git", "-C", str(target), "log", "--oneline", "-5"],
                    capture_output=True, text=True, timeout=10,
                ).stdout.strip()
                results.append({
                    "name": target.name,
                    "path": str(target),
                    "branch": branch,
                    "dirty": bool(status),
                    "uncommitted_files": len([l for l in status.split("\n") if l]) if status else 0,
                    "recent_commits": log.split("\n") if log else [],
                })
            except Exception as exc:
                results.append({"name": target.name, "error": str(exc)})

        return json.dumps({"success": True, "repos": results, "count": len(results)})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


def repo_search(pattern: str, name: str = "", include: str = "") -> str:
    """Search across cloned repos.

    Args:
        pattern: Grep pattern to search for.
        name: Limit to a specific repo (empty = all repos).
        include: File glob filter (e.g. ``*.py``).
    """
    try:
        repos_dir = _get_repos_dir()
        results: list[dict[str, Any]] = []

        targets = [repos_dir / name] if name else sorted(repos_dir.iterdir())
        for target in targets:
            if not target.is_dir() or not (target / ".git").exists():
                continue
            cmd = ["git", "-C", str(target), "grep", "-n", pattern]
            if include:
                cmd.extend(["--", include])
            try:
                grep_result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60,
                )
                if grep_result.stdout:
                    lines = grep_result.stdout.rstrip().split("\n")
                    results.append({
                        "repo": target.name,
                        "matches": len(lines),
                        "lines": lines[:50],
                        "truncated": len(lines) > 50,
                    })
            except Exception:
                pass

        return json.dumps({
            "success": True,
            "results": results,
            "total_matches": sum(r["matches"] for r in results),
        })
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


def repo_exec(name: str, command: str) -> str:
    """Run a git command in a cloned repo.

    Args:
        name: Repo name (must already be cloned).
        command: Git command to run (e.g. ``pull``, ``log --oneline -10``).
    """
    try:
        repos_dir = _get_repos_dir()
        target = repos_dir / name
        if not target.exists() or not (target / ".git").exists():
            return json.dumps({"success": False, "error": f"Repo '{name}' not found"})

        result = subprocess.run(
            ["git", "-C", str(target)] + command.split(),
            capture_output=True, text=True, timeout=120,
        )
        return json.dumps({
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "Command timed out"})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


def repo_list() -> str:
    """List all cloned repositories."""
    try:
        repos_dir = _get_repos_dir()
        repos = []
        for entry in sorted(repos_dir.iterdir()):
            if entry.is_dir() and (entry / ".git").exists():
                repos.append({
                    "name": entry.name,
                    "path": str(entry),
                    "size_kb": sum(f.stat().st_size for f in entry.rglob("*") if f.is_file()) // 1024,
                })
        return json.dumps({"success": True, "repos": repos, "count": len(repos)})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ---- Register tools -------------------------------------------------------

for _tool_def in [
    {
        "name": "repo_clone",
        "description": "Clone a git repository into the workspace for multi-repo orchestration.",
        "properties": {
            "url": {"type": "string", "description": "Git remote URL"},
            "path": {"type": "string", "description": "Optional local directory name"},
            "branch": {"type": "string", "description": "Optional branch/tag to checkout"},
            "depth": {"type": "integer", "description": "Shallow clone depth (0=full)"},
        },
        "required": ["url"],
        "handler": repo_clone,
        "emoji": "📦",
    },
    {
        "name": "repo_status",
        "description": "Show git status for one or all cloned repos (branch, dirty files, recent commits).",
        "properties": {
            "name": {"type": "string", "description": "Repo name (empty = all repos)"},
        },
        "required": [],
        "handler": repo_status,
        "emoji": "📊",
    },
    {
        "name": "repo_search",
        "description": "Search for a pattern across all cloned repositories using git grep.",
        "properties": {
            "pattern": {"type": "string", "description": "Search pattern"},
            "name": {"type": "string", "description": "Limit to specific repo"},
            "include": {"type": "string", "description": "File glob filter (e.g. *.py)"},
        },
        "required": ["pattern"],
        "handler": repo_search,
        "emoji": "🔍",
    },
    {
        "name": "repo_exec",
        "description": "Run a git command in a cloned repository (pull, log, checkout, etc.).",
        "properties": {
            "name": {"type": "string", "description": "Repo name"},
            "command": {"type": "string", "description": "Git command (e.g. 'pull', 'log --oneline -5')"},
        },
        "required": ["name", "command"],
        "handler": repo_exec,
        "emoji": "⚡",
    },
    {
        "name": "repo_list",
        "description": "List all cloned repositories in the workspace.",
        "properties": {},
        "required": [],
        "handler": repo_list,
        "emoji": "📂",
    },
]:
    registry.register(
        name=_tool_def["name"],
        toolset="multi_repo",
        schema={
            "name": _tool_def["name"],
            "description": _tool_def["description"],
            "parameters": {
                "type": "object",
                "properties": _tool_def["properties"],
                "required": _tool_def["required"],
            },
        },
        handler=lambda args, **_kw, h=_tool_def["handler"]: h(**args),
        emoji=_tool_def.get("emoji", ""),
    )
