"""``alex exec`` — headless agent execution.

Sends a prompt (or conversation history) to the agent and returns the
response. Designed for scripting, CI/CD, and SDK integration.

Usage::

    alex exec --prompt "What is 2+2?"
    alex exec --json --prompt "Summarize this" --model gpt-5.5
    alex exec --messages-file history.json --json
    echo "Summarize the repo" | alex exec --json --stdin
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def exec_command(args) -> None:
    """Entry point for ``alex exec``."""
    if not args.json:
        _run_plain(args)
    else:
        _run_json(args)


def _resolve_prompt(args) -> str:
    if args.stdin:
        return sys.stdin.read().strip()
    if args.messages_file:
        return ""
    return args.prompt


def _resolve_messages(args) -> list[dict] | None:
    if args.messages_file:
        p = Path(args.messages_file)
        if not p.exists():
            print(json.dumps({"success": False, "error": f"Messages file not found: {args.messages_file}"}))
            sys.exit(1)
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _get_toolset_list(raw: str) -> list[str] | None:
    if not raw:
        return None
    return [t.strip() for t in raw.split(",") if t.strip()]


def _run_plain(args) -> None:
    prompt = _resolve_prompt(args)

    if args.workdir:
        os.chdir(args.workdir)

    config = _build_config(args)

    if args.messages_file:
        messages = _resolve_messages(args)
        if messages:
            result = _run_agent_with_messages(messages, config, args)
        else:
            _die("--messages-file specified but no messages loaded")
            return
    else:
        result = _run_agent_with_prompt(prompt, config, args)

    if result.success:
        print(result.content)
    else:
        print(result.content, file=sys.stderr)
        sys.exit(1)


def _run_json(args) -> None:
    prompt = _resolve_prompt(args)

    if args.workdir:
        os.chdir(args.workdir)

    config = _build_config(args)

    if args.messages_file:
        messages = _resolve_messages(args)
        if messages:
            result = _run_agent_with_messages(messages, config, args)
        else:
            _json_exit({"success": False, "error": "--messages-file specified but no messages loaded"})
            return
    else:
        result = _run_agent_with_prompt(prompt, config, args)

    output = {
        "success": result.success,
        "content": result.content,
        "status": result.status.value,
        "session_id": result.session_id,
        "iterations_used": result.iterations_used,
        "total_cost_usd": result.total_cost_usd,
        "error": result.error,
        "metadata": result.metadata,
    }
    print(json.dumps(output, ensure_ascii=False, default=str))


def _build_config(args):
    from dataclasses import dataclass

    @dataclass
    class _ExecConfig:
        model: str
        provider: str
        base_url: str
        api_key: str
        api_mode: str
        max_iterations: int
        toolsets: list[str] | None
        disabled_toolsets: list[str] | None
        system_prompt: str
        temperature: float | None
        max_tokens: int | None
        reasoning_effort: str
        timeout: int
        quiet: bool

    return _ExecConfig(
        model=args.model,
        provider=args.provider,
        base_url=getattr(args, "base_url", ""),
        api_key=getattr(args, "api_key", ""),
        api_mode=getattr(args, "api_mode", ""),
        max_iterations=args.max_iterations,
        toolsets=_get_toolset_list(args.toolsets),
        disabled_toolsets=_get_toolset_list(args.disabled_toolsets),
        system_prompt=args.system,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        reasoning_effort=args.reasoning_effort,
        timeout=args.timeout,
        quiet=args.quiet,
    )


def _run_agent_with_prompt(prompt: str, config, args) -> "AgentResult":
    """Run a single-prompt agent interaction."""
    return _run_agent_internal(prompt=prompt, messages=None, config=config, args=args)


def _run_agent_with_messages(messages: list[dict], config, args) -> "AgentResult":
    """Run with a full conversation history."""
    return _run_agent_internal(prompt="", messages=messages, config=config, args=args)


def _run_agent_internal(
    prompt: str,
    messages: list[dict] | None,
    config,
    args,
) -> "AgentResult":
    """Core execution — configures and runs the AIAgent."""
    from run_agent import AIAgent
    from alex_sdk.models import AgentResult, AgentStatus

    try:
        import alex_cli.config as cfg
        config_data = cfg.load_config()
    except Exception:
        config_data = {}

    enabled_toolsets = config.toolsets
    if enabled_toolsets is None:
        enabled_toolsets = config_data.get("tools", {}).get(
            "cli", {}
        ).get("enabled", None)

    agent_kwargs = {
        "model": config.model or "",
        "provider": config.provider or "",
        "max_iterations": config.max_iterations or 90,
        "enabled_toolsets": enabled_toolsets,
        "disabled_toolsets": config.disabled_toolsets,
        "quiet_mode": config.quiet,
        "skip_context_files": False,
        "skip_memory": False,
    }

    if config.system_prompt:
        agent_kwargs["system_message"] = config.system_prompt
    if config.temperature is not None:
        agent_kwargs["temperature"] = config.temperature
    if config.max_tokens is not None:
        agent_kwargs["max_tokens"] = config.max_tokens

    try:
        agent = AIAgent(**agent_kwargs)
    except Exception as exc:
        return AgentResult(
            success=False,
            content="",
            status=AgentStatus.FAILED,
            error=f"Failed to initialize agent: {exc}",
        )

    try:
        if messages:
            result = agent.run_conversation(
                user_message=prompt or messages[-1].get("content", ""),
                conversation_history=messages[:-1] if len(messages) > 1 else None,
            )
        else:
            result = agent.run_conversation(user_message=prompt)

        final_response = result.get("final_response", "")
        return AgentResult(
            success=True,
            content=final_response,
            status=AgentStatus.COMPLETED,
            session_id=result.get("session_id"),
            iterations_used=result.get("iterations_used", 0),
            total_cost_usd=result.get("total_cost_usd", 0.0),
            metadata=result.get("metadata", {}),
        )
    except Exception as exc:
        return AgentResult(
            success=False,
            content=str(exc),
            status=AgentStatus.FAILED,
            error=str(exc),
        )


def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def _json_exit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False))
    sys.exit(1 if not data.get("success") else 0)
