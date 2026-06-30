"""Resolve ALEX_HOME for standalone skill scripts.

Skill scripts may run outside the Alex process (e.g. system Python,
nix env, CI) where ``alex_constants`` is not importable.  This module
provides the same ``get_alex_home()`` and ``display_alex_home()``
contracts as ``alex_constants`` without requiring it on ``sys.path``.

When ``alex_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``alex_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``ALEX_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from alex_constants import display_alex_home as display_alex_home
    from alex_constants import get_alex_home as get_alex_home
except (ModuleNotFoundError, ImportError):

    def get_alex_home() -> Path:
        """Return the Alex home directory (default: ~/.alex).

        Mirrors ``alex_constants.get_alex_home()``."""
        val = os.environ.get("ALEX_HOME", "").strip()
        return Path(val) if val else Path.home() / ".alex"

    def display_alex_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``alex_constants.display_alex_home()``."""
        home = get_alex_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
