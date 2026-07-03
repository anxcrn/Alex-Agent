from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from alex_sdk.exceptions import (
    AgentExecutionError,
    AgentNotFoundError,
    AgentTimeoutError,
    AgentUnauthorizedError,
)
from alex_sdk.models import AgentConfig, AgentResult, AgentStatus, ConversationMessage

logger = logging.getLogger(__name__)

_ALEX_EXEC_PATH: str | None = None


def _resolve_alex_exec() -> str:
    global _ALEX_EXEC_PATH
    if _ALEX_EXEC_PATH:
        return _ALEX_EXEC_PATH
    candidates = [
        os.environ.get("ALEX_EXEC_PATH", ""),
        os.path.join(os.path.dirname(sys.executable), "alex"),
        os.path.join(os.path.dirname(sys.executable), "alex.exe"),
        os.path.join(sys.prefix, "bin", "alex"),
        os.path.join(sys.prefix, "Scripts", "alex.exe"),
        "alex",
    ]
    for c in candidates:
        if not c:
            continue
        try:
            result = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                _ALEX_EXEC_PATH = c
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    msg = "Could not find alex executable. Set ALEX_EXEC_PATH or ensure it is on PATH."
    raise FileNotFoundError(msg)


class AlexClient:
    """Synchronous SDK client for Alex Agent.

    Spawns the agent as a subprocess (``alex exec``) for each request.
    Suitable for CI/CD pipelines, scripts, and one-shot automation.
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        alex_path: str | None = None,
        timeout: int = 300,
    ):
        self.config = config or AgentConfig()
        self._alex_path = alex_path or _resolve_alex_exec()
        self.timeout = timeout

    def run(
        self,
        prompt: str,
        *,
        config: AgentConfig | None = None,
        timeout: int | None = None,
    ) -> AgentResult:
        """Run a single agent interaction synchronously.

        Args:
            prompt: The user message to send.
            config: Optional per-call config override.
            timeout: Override the default timeout in seconds.

        Returns:
            AgentResult with the agent's response.
        """
        effective_config = config or self.config
        effective_timeout = timeout or self.timeout

        args = [
            self._alex_path, "exec",
            "--json",
            "--prompt", prompt,
        ]
        if effective_config.model:
            args.extend(["--model", effective_config.model])
        if effective_config.provider:
            args.extend(["--provider", effective_config.provider])
        if effective_config.max_iterations:
            args.extend(["--max-iterations", str(effective_config.max_iterations)])
        if effective_config.enabled_toolsets:
            args.extend(["--toolsets", ",".join(effective_config.enabled_toolsets)])
        if effective_config.disabled_toolsets:
            args.extend(["--disabled-toolsets", ",".join(effective_config.disabled_toolsets)])
        if effective_config.working_directory:
            args.extend(["--workdir", effective_config.working_directory])
        if effective_config.system_prompt:
            args.extend(["--system", effective_config.system_prompt])
        if effective_config.reasoning_effort:
            args.extend(["--reasoning-effort", effective_config.reasoning_effort])
        if effective_config.temperature is not None:
            args.extend(["--temperature", str(effective_config.temperature)])
        if effective_config.max_tokens is not None:
            args.extend(["--max-tokens", str(effective_config.max_tokens)])

        env = os.environ.copy()
        for k, v in effective_config.environment.items():
            env[k] = v

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                content="",
                status=AgentStatus.TIMEOUT,
                error=f"Agent execution timed out after {effective_timeout}s",
            )

        if result.returncode != 0:
            return AgentResult(
                success=False,
                content=result.stdout,
                status=AgentStatus.FAILED,
                error=result.stderr or "Non-zero exit code",
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return AgentResult(
                success=False,
                content=result.stdout,
                status=AgentStatus.FAILED,
                error="Failed to parse JSON output",
            )

        return AgentResult(
            success=data.get("success", True),
            content=data.get("content", ""),
            status=AgentStatus(data.get("status", "completed")),
            session_id=data.get("session_id"),
            iterations_used=data.get("iterations_used", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        config: AgentConfig | None = None,
        timeout: int | None = None,
    ) -> AgentResult:
        """Send a full conversation history.

        Args:
            messages: List of {role, content} dicts.
            config: Optional per-call config override.
            timeout: Override the default timeout in seconds.

        Returns:
            AgentResult with the assistant's final response.
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(messages, f, ensure_ascii=False)
            msgs_path = f.name

        try:
            effective_config = config or self.config
            effective_timeout = timeout or self.timeout

            args = [
                self._alex_path, "exec",
                "--json",
                "--messages-file", msgs_path,
            ]
            if effective_config.model:
                args.extend(["--model", effective_config.model])
            if effective_config.provider:
                args.extend(["--provider", effective_config.provider])
            if effective_config.max_iterations:
                args.extend(["--max-iterations", str(effective_config.max_iterations)])
            if effective_config.enabled_toolsets:
                args.extend(["--toolsets", ",".join(effective_config.enabled_toolsets)])
            if effective_config.system_prompt:
                args.extend(["--system", effective_config.system_prompt])

            env = os.environ.copy()
            for k, v in effective_config.environment.items():
                env[k] = v

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env=env,
            )
        finally:
            try:
                os.unlink(msgs_path)
            except OSError:
                pass

        if result.returncode != 0:
            return AgentResult(
                success=False,
                content=result.stdout,
                status=AgentStatus.FAILED,
                error=result.stderr or "Non-zero exit code",
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return AgentResult(
                success=False,
                content=result.stdout,
                status=AgentStatus.FAILED,
                error="Failed to parse JSON output",
            )

        return AgentResult(
            success=data.get("success", True),
            content=data.get("content", ""),
            status=AgentStatus(data.get("status", "completed")),
            session_id=data.get("session_id"),
            iterations_used=data.get("iterations_used", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            error=data.get("error"),
            messages=[ConversationMessage(**m) for m in data.get("messages", [])]
            if "messages" in data
            else None,
            metadata=data.get("metadata", {}),
        )


class AsyncAlexClient:
    """Asynchronous SDK client stub for future async support.

    Currently wraps the synchronous client. Will use HTTP-based
    Managed Agents API when available.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        self._sync = AlexClient(*args, **kwargs)
        self._loop = None

    async def run(
        self,
        prompt: str,
        *,
        config: AgentConfig | None = None,
        timeout: int | None = None,
    ) -> AgentResult:
        return await self._thread_exec(self._sync.run, prompt, config=config, timeout=timeout)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        config: AgentConfig | None = None,
        timeout: int | None = None,
    ) -> AgentResult:
        return await self._thread_exec(self._sync.chat, messages, config=config, timeout=timeout)

    async def _thread_exec(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
