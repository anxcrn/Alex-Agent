"""``alex managed-agent`` subcommand parser.

Start, stop, and monitor the Managed Agents HTTP API server.
"""

from __future__ import annotations

from typing import Callable


def build_managed_agent_parser(subparsers, *, cmd_managed_agent: Callable) -> None:
    """Attach the ``managed-agent`` subcommand to ``subparsers``."""
    parser = subparsers.add_parser(
        "managed-agent",
        aliases=["ma"],
        help="Managed Agents HTTP API server",
        description=(
            "Start, stop, and monitor the Managed Agents HTTP API server. "
            "Provides a REST API for running agents programmatically."
        ),
    )
    sub = parser.add_subparsers(dest="managed_agent_action")

    start = sub.add_parser("start", help="Start the Managed Agents API server")
    start.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    start.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    start.add_argument("--daemon", action="store_true", help="Run as background process")

    status_sub = sub.add_parser("status", help="Show Managed Agents server status")

    stop_sub = sub.add_parser("stop", help="Stop the Managed Agents API server")

    parser.set_defaults(func=cmd_managed_agent)
