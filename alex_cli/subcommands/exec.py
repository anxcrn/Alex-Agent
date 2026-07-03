"""``alex exec`` subcommand parser.

Headless agent execution for scripts, CI/CD, and SDK integration.
"""

from __future__ import annotations

from typing import Callable


def build_exec_parser(subparsers, *, cmd_exec: Callable) -> None:
    """Attach the ``exec`` subcommand to ``subparsers``."""
    exec_parser = subparsers.add_parser(
        "exec",
        help="Headless agent execution for scripts and automation",
        description=(
            "Run the agent in headless mode — no banner, no spinner, no TUI. "
            "Output is plain text (default) or JSON (--json). "
            "Designed for scripting, CI/CD pipelines, and SDK integration."
        ),
    )

    # Input source (mutually exclusive)
    input_group = exec_parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--prompt", "-p",
        default="",
        help="Single prompt string to execute",
    )
    input_group.add_argument(
        "--messages-file", "-f",
        default="",
        help="Path to a JSON file containing a list of {role, content} messages",
    )
    input_group.add_argument(
        "--stdin", "-i",
        action="store_true",
        help="Read prompt from stdin",
    )

    # Output format
    exec_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output structured JSON (includes status, cost, session_id)",
    )

    # Agent config overrides
    exec_parser.add_argument("--model", default="", help="Model to use")
    exec_parser.add_argument("--provider", default="", help="Provider to use")
    exec_parser.add_argument("--base-url", default="", help="API base URL")
    exec_parser.add_argument("--api-key", default="", help="API key")
    exec_parser.add_argument("--api-mode", default="", help="API mode (chat_completions, codex_responses, anthropic_messages)")
    exec_parser.add_argument("--max-iterations", type=int, default=0, help="Max tool-calling iterations")
    exec_parser.add_argument("--toolsets", default="", help="Comma-separated enabled toolsets")
    exec_parser.add_argument("--disabled-toolsets", default="", help="Comma-separated disabled toolsets")
    exec_parser.add_argument("--system", "-s", default="", help="System prompt override")
    exec_parser.add_argument("--temperature", type=float, default=None, help="Model temperature")
    exec_parser.add_argument("--max-tokens", type=int, default=None, help="Max response tokens")
    exec_parser.add_argument("--reasoning-effort", default="", help="Reasoning effort level")
    exec_parser.add_argument("--workdir", "-w", default="", help="Working directory")
    exec_parser.add_argument("--timeout", type=int, default=300, help="Wall-clock timeout in seconds")
    exec_parser.add_argument("--quiet", "-q", action="store_true", help="Suppress stderr diagnostics")

    exec_parser.set_defaults(func=cmd_exec)
