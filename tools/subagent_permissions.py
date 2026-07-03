"""Scoped subagent permissions — RBAC-lite for delegated agent roles.

Provides per-role tool allow/block lists that constrain what tools a
subagent can use. Roles are defined in config under
``security.subagent_roles``.

Example config::

    security:
      subagent_roles:
        auditor:
          allow_toolsets: ["file", "web", "search"]
          deny_toolsets: ["terminal", "browser", "delegation", "code_execution"]
        coder:
          allow_toolsets: ["file", "terminal", "browser", "code_execution"]
          deny_toolsets: ["delegation", "messaging", "gateway"]
        researcher:
          allow_toolsets: ["web", "search", "file"]
          deny_toolsets: ["terminal", "browser", "delegation", "code_execution"]

Integration with ``delegate_tool.py``:

    from tools.subagent_permissions import apply_role_restrictions

    def spawn_child(...):
        if role in ("auditor", "coder", "researcher"):
            enabled, disabled = apply_role_restrictions(role, enabled_toolsets)
            ...
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Built-in role definitions (fallback if config not loaded)
_BUILTIN_ROLES: dict[str, dict[str, list[str]]] = {
    "auditor": {
        "allow_toolsets": ["file", "web", "search"],
        "deny_toolsets": ["terminal", "browser", "delegation", "code_execution", "workflow"],
    },
    "coder": {
        "allow_toolsets": ["file", "terminal", "browser", "code_execution", "web"],
        "deny_toolsets": ["delegation", "messaging", "gateway", "workflow"],
    },
    "researcher": {
        "allow_toolsets": ["web", "search", "file", "x_search"],
        "deny_toolsets": ["terminal", "browser", "delegation", "code_execution", "workflow"],
    },
    "planner": {
        "allow_toolsets": ["file", "web", "search", "workflow", "delegation"],
        "deny_toolsets": ["terminal", "browser", "code_execution"],
    },
    "reviewer": {
        "allow_toolsets": ["file", "web", "search"],
        "deny_toolsets": ["terminal", "browser", "delegation", "code_execution", "workflow"],
    },
}


def _load_roles_from_config() -> dict[str, dict[str, list[str]]]:
    """Load role definitions from config, falling back to built-ins."""
    try:
        from alex_cli.config import load_config

        config = load_config()
        roles = config.get("security", {}).get("subagent_roles", {})
        if roles:
            return roles
    except Exception as exc:
        logger.debug("Could not load subagent roles from config: %s", exc)
    return _BUILTIN_ROLES


def get_role_definitions() -> dict[str, dict[str, list[str]]]:
    """Get all available role definitions."""
    return _load_roles_from_config()


def apply_role_restrictions(
    role: str,
    current_toolsets: list[str] | None = None,
) -> tuple[list[str] | None, list[str] | None]:
    """Apply role-based tool restrictions.

    Args:
        role: The subagent role name (auditor, coder, researcher, etc.).
        current_toolsets: The currently enabled toolsets (or ``None`` for all).

    Returns:
        Tuple of ``(enabled_toolsets, disabled_toolsets)`` where
        ``enabled_toolsets`` is ``None`` (inherit all) or restricted to
        the role's allowed set; ``disabled_toolsets`` includes the role's
        denied toolsets.
    """
    roles = _load_roles_from_config()
    role_def = roles.get(role)
    if not role_def:
        logger.debug("Unknown subagent role %r, no restrictions applied", role)
        return current_toolsets, None

    allow = role_def.get("allow_toolsets", [])
    deny = role_def.get("deny_toolsets", [])

    # If allow_toolsets is specified, restrict to intersection
    if allow:
        if current_toolsets:
            enabled = [t for t in current_toolsets if t in allow]
        else:
            enabled = list(allow)
    else:
        enabled = current_toolsets

    # Always add deny_toolsets to the disabled list
    disabled = deny[:] if deny else None

    logger.debug(
        "Role %r restrictions applied: enabled=%s, disabled=%s",
        role,
        enabled,
        disabled,
    )

    return enabled, disabled


def check_tool_allowed(role: str, tool_name: str) -> bool:
    """Check whether a specific tool is allowed for a given role."""
    roles = _load_roles_from_config()
    role_def = roles.get(role)
    if not role_def:
        return True

    from toolsets import TOOLSETS

    # Find which toolset this tool belongs to
    toolset_name = None
    for ts_name, ts_def in TOOLSETS.items():
        if tool_name in ts_def.get("tools", []):
            toolset_name = ts_name
            break

    if toolset_name:
        deny = role_def.get("deny_toolsets", [])
        if toolset_name in deny:
            return False
        allow = role_def.get("allow_toolsets", [])
        if allow and toolset_name not in allow:
            return False

    return True
