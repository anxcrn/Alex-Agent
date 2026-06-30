"""Welcome banner, ASCII art, skills summary, and update check for the CLI.

Pure display functions with no AlexCLI state dependency.
"""

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from alex_constants import get_alex_home
from typing import TYPE_CHECKING, Dict, List, Optional

# rich and prompt_toolkit are imported lazily (inside the functions that use
# them) rather than at module level.  Importing this module is on the TUI
# gateway's critical startup path purely to reach the lightweight update-check
# helpers (``prefetch_update_check``); pulling rich.console + prompt_toolkit
# eagerly added ~50ms of wasted imports before ``gateway.ready`` could fire.
# Keep the type-only reference available to checkers without the runtime cost.
if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)


# =========================================================================
# ANSI building blocks for conversation display
# =========================================================================

_GOLD = "\033[1;38;2;255;215;0m"  # True-color #FFD700 bold
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RST = "\033[0m"


def cprint(text: str):
    """Print ANSI-colored text through prompt_toolkit's renderer."""
    from prompt_toolkit import print_formatted_text as _pt_print
    from prompt_toolkit.formatted_text import ANSI as _PT_ANSI
    _pt_print(_PT_ANSI(text))


# =========================================================================
# Skin-aware color helpers
# =========================================================================

def _skin_color(key: str, fallback: str) -> str:
    """Get a color from the active skin, or return fallback."""
    try:
        from alex_cli.skin_engine import get_active_skin
        return get_active_skin().get_color(key, fallback)
    except Exception:
        return fallback
# =========================================================================
# ASCII Art & Branding
# =========================================================================

from alex_cli import __version__ as VERSION, __release_date__ as RELEASE_DATE

ALEX_AGENT_LOGO = """[bold #BF5FFF] █████╗ ██╗     ███████╗██╗  ██╗       █████╗  ██████╗ ███████╗███╗   ██╗████████╗[/]
[bold #A855F7]██╔══██╗██║     ██╔════╝╚██╗██╔╝      ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝[/]
[#9333EA]███████║██║     █████╗   ╚███╔╝ █████╗███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║[/]
[#7C3AED]██╔══██║██║     ██╔══╝   ██╔██╗ ╚════╝██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║[/]
[#6D28D9]██║  ██║███████╗███████╗██╔╝ ██╗      ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║[/]
[#5B21B6]╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝      ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝[/]
[dim #7C3AED]  TACTICAL AI · AUTONOMOUS · ADAPTIVE · UNSTOPPABLE[/]"""

ALEX_CADUCEUS = """[#6D28D9]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣤⣤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#7C3AED]⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣿⠟⠻⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#9333EA]⠀⠀⠀⠀⠀⠀⣠⣾⡿⠋⠀⠀⠀⠙⢿⣷⣄⠀⠀⠀⠀⠀⠀⠀[/]
[#9333EA]⠀⠀⠀⠀⢀⣾⡿⠋⠀⠀⢠⡄⠀⠀⠀⠙⢿⣷⡀⠀⠀⠀⠀⠀[/]
[#A855F7]⠀⠀⠀⣰⣿⠟⠀⠀⠀⣰⣿⣿⣆⠀⠀⠀⠻⣿⣆⠀⠀⠀⠀[/]
[#A855F7]⠀⠀⢰⣿⠏⠀⠀⢀⣾⡿⠉⢿⣷⡀⠀⠀⠀⠹⣿⡆⠀⠀⠀[/]
[#BF5FFF]⠀⠀⣿⡟⠀⠀⣠⣿⠟⠀⠀⠀⠻⣿⣄⠀⠀⠀⢻⣿⠀⠀⠀[/]
[#BF5FFF]⠀⠀⣿⡇⠀⠀⠙⠋⠀⠀⚔⠀⠀⠙⠋⠀⠀⠀⢸⣿⠀⠀⠀[/]
[#7C3AED]⠀⠀⢿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⡿⠀⠀⠀[/]
[#6D28D9]⠀⠀⠘⢿⣷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⡿⠃⠀⠀⠀[/]
[#5B21B6]⠀⠀⠀⠈⠻⢿⣷⣦⣄⣀⠀⠀⣀⣠⣴⣾⡿⠟⠁⠀⠀⠀⠀[/]
[#4C1D95]⠀⠀⠀⠀⠀⠈⠙⠻⠿⠿⠿⠿⠿⠟⠛⠉⠀⠀⠀⠀⠀⠀⠀[/]"""





# =========================================================================
# Skills scanning
# =========================================================================

def get_available_skills() -> Dict[str, List[str]]:
    """Return skills grouped by category, filtered by platform and disabled state.

    Delegates to ``_find_all_skills()`` from ``tools/skills_tool`` which already
    handles platform gating (``platforms:`` frontmatter) and respects the
    user's ``skills.disabled`` config list.
    """
    try:
        from tools.skills_tool import _find_all_skills
        all_skills = _find_all_skills()  # already filtered
    except Exception:
        return {}

    skills_by_category: Dict[str, List[str]] = {}
    for skill in all_skills:
        category = skill.get("category") or "general"
        skills_by_category.setdefault(category, []).append(skill["name"])
    return skills_by_category


# =========================================================================
# Update check
# =========================================================================

# Cache update check results for 6 hours to avoid repeated git fetches
_UPDATE_CHECK_CACHE_SECONDS = 6 * 3600

# Sentinel returned when we know an update exists but can't count commits
# (e.g. nix-built alex — no local git history to count against).
UPDATE_AVAILABLE_NO_COUNT = -1

_UPSTREAM_REPO_URL = "https://github.com/charan vankudoth/alex-agent.git"
_OFFICIAL_REPO_CANONICAL = "github.com/charan vankudoth/alex-agent"


def _canonical_github_remote(url: str | None) -> str:
    """Return ``host/owner/repo`` for common GitHub remote URL forms."""
    if not url:
        return ""
    value = url.strip()
    if value.startswith("git@github.com:"):
        value = "github.com/" + value[len("git@github.com:"):]
    elif value.startswith("ssh://git@github.com/"):
        value = "github.com/" + value[len("ssh://git@github.com/"):]
    else:
        parsed = urlparse(value)
        if parsed.netloc and parsed.path:
            value = f"{parsed.netloc}{parsed.path}"
    value = value.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value.lower()


def _is_ssh_remote(url: str | None) -> bool:
    if not url:
        return False
    value = url.strip().lower()
    return value.startswith("git@") or value.startswith("ssh://")


def _is_official_ssh_remote(url: str | None) -> bool:
    return _is_ssh_remote(url) and _canonical_github_remote(url) == _OFFICIAL_REPO_CANONICAL


def _git_stdout(args: list[str], *, cwd: Path, timeout: int = 5) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip()


def _check_via_rev(local_rev: str) -> Optional[int]:
    """Compare an embedded git revision to upstream main via ls-remote.

    Returns 0 if up-to-date, ``UPDATE_AVAILABLE_NO_COUNT`` if behind,
    or ``None`` on failure.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", _UPSTREAM_REPO_URL, "refs/heads/main"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    upstream_rev = result.stdout.split()[0]
    if not upstream_rev:
        return None
    return 0 if upstream_rev == local_rev else UPDATE_AVAILABLE_NO_COUNT


def _check_via_local_git(repo_dir: Path) -> Optional[int]:
    """Count commits behind origin/main in a local checkout."""
    origin_url = _git_stdout(["remote", "get-url", "origin"], cwd=repo_dir)
    if _is_official_ssh_remote(origin_url):
        head_rev = _git_stdout(["rev-parse", "HEAD"], cwd=repo_dir)
        checked = _check_via_rev(head_rev) if head_rev else None
        if checked == UPDATE_AVAILABLE_NO_COUNT:
            return 1
        return checked

    # Installer checkouts are shallow (`git clone --depth 1`). On a shallow
    # clone the history stops at a single commit, so a plain `git fetch` would
    # unshallow the repo (dragging in the whole history) and
    # `rev-list --count HEAD..origin/main` would report a huge bogus "behind"
    # number (e.g. "12492 commits behind"). Detect shallow up front: fetch with
    # --depth 1 to preserve the boundary and compare tip SHAs instead of
    # counting. Full clones (developers, Docker dev images) keep the exact
    # count path unchanged. Mirrors the desktop fix in apps/desktop/electron/main.cjs.
    shallow = _git_stdout(["rev-parse", "--is-shallow-repository"], cwd=repo_dir)
    is_shallow = shallow == "true"

    try:
        fetch_args = ["git", "fetch", "origin"]
        if is_shallow:
            fetch_args += ["--depth", "1"]
        fetch_args.append("--quiet")
        subprocess.run(
            fetch_args,
            capture_output=True, timeout=10,
            cwd=str(repo_dir),
        )
    except Exception:
        pass  # Offline or timeout — use stale refs, that's fine

    if is_shallow:
        # No history to count across the shallow boundary. `origin/main` may not
        # be a tracking ref in a `clone --depth 1`, so prefer FETCH_HEAD (just
        # updated by the fetch above) and fall back to origin/main.
        head_rev = _git_stdout(["rev-parse", "HEAD"], cwd=repo_dir)
        target_rev = (
            _git_stdout(["rev-parse", "FETCH_HEAD"], cwd=repo_dir)
            or _git_stdout(["rev-parse", "origin/main"], cwd=repo_dir)
        )
        if not head_rev or not target_rev:
            return None
        return 0 if head_rev == target_rev else UPDATE_AVAILABLE_NO_COUNT

    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True, text=True, timeout=5,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return None


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse '0.13.0' into (0, 13, 0) for comparison. Non-numeric segments become 0."""
    parts = []
    for segment in v.split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _fetch_pypi_latest(package: str = "alex-agent") -> Optional[str]:
    """Fetch the latest version of a package from PyPI. Returns None on failure."""
    try:
        import urllib.request
        url = f"https://pypi.org/pypi/{package}/json"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("info", {}).get("version")
    except Exception:
        return None


def check_via_pypi() -> Optional[int]:
    """Compare installed version against PyPI latest.

    Returns 0 if up-to-date, 1 if behind, None on failure.
    """
    latest = _fetch_pypi_latest()
    if latest is None:
        return None
    if latest == VERSION:
        return 0
    try:
        if _version_tuple(latest) > _version_tuple(VERSION):
            return 1
        return 0
    except Exception:
        return 1 if latest != VERSION else 0


def check_for_updates() -> Optional[int]:
    """Check whether a Alex update is available.

    Two paths: if ``ALEX_REVISION`` is set (nix builds embed it), compare
    it to upstream main via ``git ls-remote``. Otherwise look for a local
    git checkout and count commits behind ``origin/main``.

    Returns the number of commits behind, ``UPDATE_AVAILABLE_NO_COUNT`` (-1)
    if behind but the count is unknown, ``0`` if up-to-date, or ``None`` if
    the check failed or doesn't apply. Cached for 6 hours.
    """
    alex_home = get_alex_home()
    cache_file = alex_home / ".update_check"
    embedded_rev = os.environ.get("ALEX_REVISION") or None

    # Docker images have no working tree to count commits against — the
    # published image excludes `.git` (see .dockerignore) and sets no
    # ALEX_REVISION (that's nix-only). Without this guard the checks below
    # fall through to `check_via_pypi()`, whose PyPI-version mismatch flag (1)
    # then gets rendered by the CLI banner and the TUI badge as a phantom
    # "1 commit behind" — even though no git repo or commit math is involved,
    # and `alex update` correctly refuses to run in-place inside the
    # container anyway. The dashboard's REST `/api/alex/update/check`
    # endpoint already short-circuits docker the same way (web_server.py);
    # mirror that here so the banner/TUI surfaces agree. Returning None makes
    # both the Rich banner (build_welcome_banner) and the Ink badge
    # (branding.tsx, guarded on `typeof === 'number' && > 0`) show nothing.
    try:
        from alex_cli.config import detect_install_method
        if detect_install_method() == "docker":
            return None
    except Exception:
        pass

    # Read cache — invalidate if the embedded rev OR installed version has
    # changed since the last check. The version guard matters for pip installs:
    # `check_via_pypi()` compares against VERSION, so a `pip install --upgrade`
    # changes VERSION but leaves rev unchanged (both None), and without this
    # the stale "behind" count would survive the upgrade for up to 6h. See #34491.
    now = time.time()
    try:
        if cache_file.exists():
            cached = json.loads(cache_file.read_text())
            if (
                now - cached.get("ts", 0) < _UPDATE_CHECK_CACHE_SECONDS
                and cached.get("rev") == embedded_rev
                and cached.get("ver") == VERSION
            ):
                return cached.get("behind")
    except Exception:
        pass

    if embedded_rev:
        behind = _check_via_rev(embedded_rev)
    else:
        # Prefer the running code's location over the profile-scoped path.
        # $ALEX_HOME/alex-agent/ may be a stale copy from --clone-all;
        # Path(__file__) always resolves to the actual installed checkout.
        repo_dir = Path(__file__).parent.parent.resolve()
        if not (repo_dir / ".git").exists():
            repo_dir = alex_home / "alex-agent"
        if not (repo_dir / ".git").exists():
            behind = check_via_pypi()
        else:
            behind = _check_via_local_git(repo_dir)

    try:
        cache_file.write_text(
            json.dumps({"ts": now, "behind": behind, "rev": embedded_rev, "ver": VERSION})
        )
    except Exception:
        pass

    return behind


def _resolve_repo_dir() -> Optional[Path]:
    """Return the active Alex git checkout, or None if this isn't a git install.

    Prefers the running code's location over the profile-scoped path
    because ``$ALEX_HOME/alex-agent/`` may be a stale copy carried
    over by ``--clone-all``.
    """
    repo_dir = Path(__file__).parent.parent.resolve()
    if not (repo_dir / ".git").exists():
        alex_home = get_alex_home()
        repo_dir = alex_home / "alex-agent"
    return repo_dir if (repo_dir / ".git").exists() else None


def _git_short_hash(repo_dir: Path, rev: str) -> Optional[str]:
    """Resolve a git revision to an 8-character short hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=8", rev],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(repo_dir),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def get_git_banner_state(repo_dir: Optional[Path] = None) -> Optional[dict]:
    """Return upstream/local git hashes for the startup banner.

    For source installs and dev images this runs ``git rev-parse`` against
    the active checkout.  When no checkout is available — the canonical case
    is the published Docker image, which excludes ``.git`` from the build
    context — we fall back to the baked-in build SHA (see
    ``alex_cli/build_info.py``) and return it as a frozen
    ``upstream == local`` state with ``ahead=0``.  A built image is by
    definition pinned to one commit, so "ahead" is always zero and the
    banner correctly shows ``· upstream <sha>`` with no carried-commits
    annotation.
    """
    repo_dir = repo_dir or _resolve_repo_dir()
    if repo_dir is None:
        # No git checkout — try the baked build SHA (Docker image path).
        try:
            from alex_cli.build_info import get_build_sha
            baked = get_build_sha(short=8)
            if baked:
                return {"upstream": baked, "local": baked, "ahead": 0}
        except Exception:
            pass
        return None

    upstream = _git_short_hash(repo_dir, "origin/main")
    local = _git_short_hash(repo_dir, "HEAD")
    if not upstream or not local:
        # Live-git lookup failed (e.g. shallow clone without origin/main).
        # Fall back to the baked build SHA if available.
        try:
            from alex_cli.build_info import get_build_sha
            baked = get_build_sha(short=8)
            if baked:
                return {"upstream": baked, "local": baked, "ahead": 0}
        except Exception:
            pass
        return None

    ahead = 0
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "origin/main..HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            ahead = int((result.stdout or "0").strip() or "0")
    except Exception:
        ahead = 0

    return {"upstream": upstream, "local": local, "ahead": max(ahead, 0)}


_RELEASE_URL_BASE = "https://github.com/charan vankudoth/alex-agent/releases/tag"
_latest_release_cache: Optional[tuple] = None  # (tag, url) once resolved


def get_latest_release_tag(repo_dir: Optional[Path] = None) -> Optional[tuple]:
    """Return ``(tag, release_url)`` for the latest git tag, or None.

    Local-only — runs ``git describe --tags --abbrev=0`` against the
    Alex checkout. Cached per-process. Release URL always points at the
    canonical charan vankudoth/alex-agent repo (forks don't get a link).
    """
    global _latest_release_cache
    if _latest_release_cache is not None:
        return _latest_release_cache or None

    repo_dir = repo_dir or _resolve_repo_dir()
    if repo_dir is None:
        _latest_release_cache = ()  # falsy sentinel — skip future lookups
        return None

    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=3,
            cwd=str(repo_dir),
        )
    except Exception:
        _latest_release_cache = ()
        return None

    if result.returncode != 0:
        _latest_release_cache = ()
        return None

    tag = (result.stdout or "").strip()
    if not tag:
        _latest_release_cache = ()
        return None

    url = f"{_RELEASE_URL_BASE}/{tag}"
    _latest_release_cache = (tag, url)
    return _latest_release_cache


def format_banner_version_label() -> str:
    """Return the version label shown in the startup banner title."""
    base = f"Alex Agent v{VERSION} ({RELEASE_DATE})"
    state = get_git_banner_state()
    if not state:
        return base

    upstream = state["upstream"]
    local = state["local"]
    ahead = int(state.get("ahead") or 0)

    if ahead <= 0 or upstream == local:
        return f"{base} · upstream {upstream}"

    carried_word = "commit" if ahead == 1 else "commits"
    return f"{base} · upstream {upstream} · local {local} (+{ahead} carried {carried_word})"


# =========================================================================
# Non-blocking update check
# =========================================================================

_update_result: Optional[int] = None
_update_check_done = threading.Event()


def prefetch_update_check():
    """Kick off update check in a background daemon thread."""
    def _run():
        global _update_result
        _update_result = check_for_updates()
        _update_check_done.set()
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def get_update_result(timeout: float = 0.5) -> Optional[int]:
    """Get result of prefetched check. Returns None if not ready."""
    _update_check_done.wait(timeout=timeout)
    return _update_result


# =========================================================================
# Welcome banner
# =========================================================================

def _format_context_length(tokens: int) -> str:
    """Format a token count for display (e.g. 128000 → '128K', 1048576 → '1M')."""
    if tokens >= 1_000_000:
        val = tokens / 1_000_000
        rounded = round(val)
        if abs(val - rounded) < 0.05:
            return f"{rounded}M"
        return f"{val:.1f}M"
    elif tokens >= 1_000:
        val = tokens / 1_000
        rounded = round(val)
        if abs(val - rounded) < 0.05:
            return f"{rounded}K"
        return f"{val:.1f}K"
    return str(tokens)


def _display_toolset_name(toolset_name: str) -> str:
    """Normalize internal/legacy toolset identifiers for banner display."""
    if not toolset_name:
        return "unknown"
    return (
        toolset_name[:-6]
        if toolset_name.endswith("_tools")
        else toolset_name
    )


def build_welcome_banner(console: "Console", model: str, cwd: str,
                         tools: List[dict] = None,
                         enabled_toolsets: List[str] = None,
                         session_id: str = None,
                         get_toolset_for_tool=None,
                         context_length: int = None):
    """Build and print a cyberpunk-themed welcome banner.

    Args:
        console: Rich Console instance.
        model: Current model name.
        cwd: Current working directory.
        tools: List of tool definitions.
        enabled_toolsets: List of enabled toolset names.
        session_id: Session identifier.
        get_toolset_for_tool: Callable to map tool name -> toolset name.
        context_length: Model's context window size in tokens.
    """
    from datetime import datetime
    from model_tools import check_tool_availability, TOOLSET_REQUIREMENTS
    from rich.panel import Panel
    from rich.table import Table
    from rich.columns import Columns
    from rich.text import Text
    if get_toolset_for_tool is None:
        from model_tools import get_toolset_for_tool

    tools = tools or []
    enabled_toolsets = enabled_toolsets or []
    now = datetime.now()

    _, unavailable_toolsets = check_tool_availability(quiet=True)
    _enabled_ts = {str(t) for t in enabled_toolsets}
    if _enabled_ts:
        unavailable_toolsets = [
            item for item in unavailable_toolsets
            if str(item.get("id", item.get("name", ""))) in _enabled_ts
        ]
    disabled_tools = set()
    lazy_tools = set()
    for item in unavailable_toolsets:
        toolset_name = item.get("name", "")
        ts_req = TOOLSET_REQUIREMENTS.get(toolset_name, {})
        tools_in_ts = item.get("tools", [])
        if ts_req.get("check_fn"):
            lazy_tools.update(tools_in_ts)
        else:
            disabled_tools.update(tools_in_ts)

    # Use skin's custom art if provided
    try:
        from alex_cli.skin_engine import get_active_skin
        _bskin = get_active_skin()
        _hero = _bskin.banner_hero if hasattr(_bskin, 'banner_hero') and _bskin.banner_hero else ALEX_CADUCEUS
    except Exception:
        _bskin = None
        _hero = ALEX_CADUCEUS

    # ── Color palette (cyberpunk purple/violet) ──
    NEON = "#BF5FFF"
    PURPLE = "#A855F7"
    DEEP = "#7C3AED"
    DARK = "#5B21B6"
    DIM_P = "#6D28D9"
    GREEN = "#4ADE80"
    CYAN = "#22D3EE"
    RED = "#F87171"
    YELLOW = "#FBBF24"
    WHITE = "#E2E8F0"
    DIM_WHITE = "#94A3B8"

    # ── Model info ──
    model_short = model.split("/")[-1] if "/" in model else model
    if model_short.endswith(".gguf"):
        model_short = model_short[:-5]
    if len(model_short) > 28:
        model_short = model_short[:25] + "..."
    ctx_str = _format_context_length(context_length) if context_length else "∞"

    # ── Toolset counting ──
    toolsets_dict: Dict[str, list] = {}
    for tool in tools:
        tool_name = tool["function"]["name"]
        toolset = _display_toolset_name(get_toolset_for_tool(tool_name) or "other")
        toolsets_dict.setdefault(toolset, []).append(tool_name)
    for item in unavailable_toolsets:
        toolset_id = item.get("id", item.get("name", "unknown"))
        display_name = _display_toolset_name(toolset_id)
        if display_name not in toolsets_dict:
            toolsets_dict[display_name] = []
        for tool_name in item.get("tools", []):
            if tool_name not in toolsets_dict[display_name]:
                toolsets_dict[display_name].append(tool_name)

    # Skills
    _skills_enabled = (not _enabled_ts) or ("skills" in _enabled_ts)
    if _skills_enabled:
        skills_by_category = get_available_skills()
        total_skills = sum(len(s) for s in skills_by_category.values())
    else:
        skills_by_category = {}
        total_skills = 0

    # MCP
    try:
        from tools.mcp_tool import get_mcp_status
        mcp_status = get_mcp_status()
    except Exception:
        mcp_status = []
    mcp_connected = sum(1 for s in mcp_status if s["connected"]) if mcp_status else 0

    total_tools = len(tools)
    total_toolsets = len(toolsets_dict)

    # ═══════════════════════════════════════════════════════════════
    # Print the logo
    # ═══════════════════════════════════════════════════════════════
    console.print()
    term_width = shutil.get_terminal_size().columns
    if term_width >= 95:
        _logo = _bskin.banner_logo if _bskin and hasattr(_bskin, 'banner_logo') and _bskin.banner_logo else ALEX_AGENT_LOGO
        console.print(_logo)

    # ═══════════════════════════════════════════════════════════════
    # Build the cyberpunk layout: LEFT column + RIGHT column
    # ═══════════════════════════════════════════════════════════════
    layout = Table.grid(padding=(0, 2))
    layout.add_column("left", ratio=1)
    layout.add_column("right", ratio=1)

    # ── LEFT COLUMN ──
    left_lines = []

    # System Status panel
    sys_status = []
    sys_status.append(f"[bold {GREEN}][✓][/] [bold {WHITE}]CORE SYSTEMS     [/][bold {GREEN}]ONLINE[/]")
    sys_status.append(f"[bold {GREEN}][✓][/] [bold {WHITE}]AI MODELS         [/][bold {GREEN}]ONLINE[/]")
    sys_status.append(f"[bold {GREEN}][✓][/] [bold {WHITE}]MEMORY ENGINE     [/][bold {GREEN}]ONLINE[/]")
    sys_status.append(f"[bold {GREEN}][✓][/] [bold {WHITE}]AGENT NETWORK     [/][bold {GREEN}]ONLINE[/]")
    sys_status.append(f"[bold {GREEN}][✓][/] [bold {WHITE}]TOOLS & PROTOCOLS  [/][bold {GREEN}]ONLINE[/]")
    sys_status.append(f"[bold {GREEN}][✓][/] [bold {WHITE}]SECURITY SHIELD   [/][bold {GREEN}]ACTIVE[/]")
    if os.getenv("ALEX_YOLO_MODE"):
        sys_status.append(f"[bold {RED}][!][/] [bold {RED}]YOLO MODE         ENGAGED[/]")
    sys_panel = Panel(
        "\n".join(sys_status),
        title=f"[bold {NEON}]─ SYSTEM STATUS ─[/]",
        border_style=DIM_P,
        padding=(0, 1),
    )
    left_lines.append(sys_panel)

    # Creator panel
    creator_lines = []
    creator_lines.append(f"[dim {DIM_WHITE}]Founder[/]")
    creator_lines.append(f"[bold {WHITE}]CHARAN VANKUDOTH[/]")
    creator_lines.append(f"[dim {DIM_WHITE}]India · Telangana · Mahabubabad[/]")
    creator_lines.append("")
    creator_lines.append(f"[bold {DIM_P}]\"[/][italic {PURPLE}]I don't seek power.[/]")
    creator_lines.append(f" [italic {PURPLE}]I seek change.[/][bold {DIM_P}]\"[/]")
    creator_panel = Panel(
        "\n".join(creator_lines),
        title=f"[bold {NEON}]─ CREATED BY ─[/]",
        border_style=DIM_P,
        padding=(0, 1),
    )
    left_lines.append(creator_panel)

    # Boot sequence
    boot_lines = []
    boot_lines.append(f"[{GREEN}]>> Initializing Alex Agent...[/]")
    boot_lines.append(f"[{GREEN}]>> Loading core modules...[/]")
    boot_lines.append(f"[{GREEN}]>> Establishing secure connection...[/]")
    progress_bar = "█" * 30
    boot_lines.append(f"[{GREEN}]>> Boot sequence [{NEON}]{progress_bar}[/{NEON}] 100%[/]")
    boot_lines.append(f"[{GREEN}]>> Welcome back, Charan.[/]")
    boot_lines.append(f"[{GREEN}]>> How can I assist you today?[/]")
    boot_lines.append("")
    boot_lines.append(f"[bold {NEON}]alex@agent:~$[/] [dim {WHITE}]▌[/]")
    boot_panel = Panel(
        "\n".join(boot_lines),
        border_style=DIM_P,
        padding=(0, 1),
    )
    left_lines.append(boot_panel)

    # ── RIGHT COLUMN ──
    right_lines = []

    # Time display
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%b %d, %Y").upper()
    day_str = now.strftime("%A").upper()
    time_panel = Panel(
        f"[bold {NEON}]{time_str}[/]\n[dim {DIM_WHITE}]{date_str}[/]\n[dim {DIM_WHITE}]{day_str}[/]",
        border_style=DIM_P,
        padding=(0, 1),
    )
    right_lines.append(time_panel)

    # Agent Capabilities
    cap_lines = []
    capabilities = [
        ("CODE ANALYSIS", "100"),
        ("THREAT DETECTION", "100"),
        ("AUTONOMOUS CODING", "100"),
        ("TASK EXECUTION", "100"),
        ("MEMORY RECALL", "100"),
        ("PATTERN RECOGNITION", "100"),
        ("ADAPTIVE LEARNING", "100"),
    ]
    for cap_name, pct in capabilities:
        bar = f"[bold {NEON}]{'█' * 12}[/]"
        cap_lines.append(f"[dim {DIM_WHITE}]> {cap_name:<22}[/] {bar} [{GREEN}]{pct}%[/]")
    cap_panel = Panel(
        "\n".join(cap_lines),
        title=f"[bold {NEON}]─ AGENT CAPABILITIES ─[/]",
        border_style=DIM_P,
        padding=(0, 1),
    )
    right_lines.append(cap_panel)

    # Active Missions
    mission_lines = []
    missions = [
        "HUNTING THE EVIL",
        "PROTECTING HUMANITY",
        "BRINGING CHANGE",
        "BUILDING THE FUTURE",
    ]
    for mission in missions:
        mission_lines.append(f"[dim {DIM_WHITE}]> {mission:<26}[/][bold {CYAN}]>>> IN PROGRESS[/]")
    mission_panel = Panel(
        "\n".join(mission_lines),
        title=f"[bold {NEON}]─ ACTIVE MISSIONS ─[/]",
        border_style=DIM_P,
        padding=(0, 1),
    )
    right_lines.append(mission_panel)

    # Core Modules
    core_lines = []
    version_label = format_banner_version_label()
    core_modules = [
        ("ALEX CORE", VERSION),
        ("AI MODEL", model_short),
        (f"CONTEXT", f"{ctx_str}"),
        (f"TOOLS", f"{total_tools}"),
        (f"SKILLS", f"{total_skills}"),
    ]
    if mcp_connected:
        core_modules.append(("MCP SERVERS", str(mcp_connected)))
    for mod_name, mod_ver in core_modules:
        core_lines.append(f"[dim {DIM_WHITE}]> {mod_name:<20}[/][bold {WHITE}]{mod_ver}[/]")
    core_panel = Panel(
        "\n".join(core_lines),
        title=f"[bold {NEON}]─ CORE MODULES ─[/]",
        border_style=DIM_P,
        padding=(0, 1),
    )
    right_lines.append(core_panel)

    # Location panel
    loc_panel = Panel(
        f"[bold {WHITE}]UNKNOWN[/]\n[dim {DIM_WHITE}]The World Is My Server[/]",
        title=f"[bold {NEON}]─ LOCATION ─[/]",
        border_style=DIM_P,
        padding=(0, 1),
    )
    right_lines.append(loc_panel)

    # Assemble left and right into renderables
    from rich.console import Group
    left_group = Group(*left_lines)
    right_group = Group(*right_lines)

    layout.add_row(left_group, right_group)

    # ── Update check ──
    update_line = ""
    try:
        behind = get_update_result(timeout=0.5)
        if behind is not None and behind != 0:
            from alex_cli.config import get_managed_update_command, recommended_update_command
            if behind > 0:
                commits_word = "commit" if behind == 1 else "commits"
                update_line = f"[bold {YELLOW}]⚠ {behind} {commits_word} behind — run {recommended_update_command()} to update[/]"
            else:
                managed_cmd = get_managed_update_command()
                update_line = f"[bold {YELLOW}]⚠ update available[/]"
                if managed_cmd:
                    update_line += f"[dim {YELLOW}] — run [bold]{managed_cmd}[/bold][/]"
    except Exception:
        pass

    # Pip warning
    try:
        from alex_cli.config import detect_install_method
        if detect_install_method() == "pip":
            update_line = (
                f"[bold {YELLOW}]⚠ pip install not officially supported[/]"
                f"[dim {YELLOW}] — may cause instability[/]"
            )
    except Exception:
        pass

    # ── Status bar at the bottom ──
    status_parts = [
        f"[bold {NEON}]◉[/] [bold {WHITE}]USER: CHARAN[/]",
        f"[bold {NEON}]◉[/] [bold {WHITE}]LEVEL: MAX[/]",
        f"[bold {NEON}]◉[/] [bold {WHITE}]TITLE: SHADOW MONARCH[/]",
        f"[bold {NEON}]◉[/] [bold {WHITE}]RANK: SSS[/]",
    ]
    status_bar = "    ".join(status_parts)

    # ── Print everything ──
    outer_panel = Panel(
        layout,
        title=f"[bold {NEON}]⟨ ALEX AGENT TERMINAL {VERSION} ⟩[/]",
        subtitle=f"[dim {DIM_P}]{status_bar}[/]",
        border_style=DEEP,
        padding=(1, 2),
    )

    console.print(outer_panel)

    if update_line:
        console.print(update_line)

    # Session info
    if session_id:
        console.print(f"[dim {DIM_WHITE}]Session: {session_id}[/]")
    console.print(f"[dim {DIM_WHITE}]{cwd}[/]")
    console.print()

