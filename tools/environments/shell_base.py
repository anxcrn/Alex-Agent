"""Unified shell environment protocol for multi-shell support.

Defines the abstract interface that every shell backend (PowerShell, cmd,
WSL, Git Bash) implements. This lets the agent choose the right shell for
each command instead of being locked to bash on all platforms.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ShellResult:
    """Standardized result from any shell execution."""
    exit_code: int
    stdout: str
    stderr: str
    command: str = ""
    shell_type: str = ""
    duration_ms: float = 0.0

    @property
    def output(self) -> str:
        return self.stdout + self.stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0


_IS_WINDOWS = platform.system() == "Windows"


class ShellEnvironment(ABC):
    """Abstract base for a command shell backend.

    Each subclass wraps a specific shell (PowerShell, cmd.exe, WSL bash,
    Git Bash) and provides a uniform ``run()`` interface.  The agent calls
    ``run(command)`` and gets back a ``ShellResult`` regardless of which
    shell is active.
    """

    def __init__(self, cwd: str = "", env: dict[str, str] | None = None):
        self._cwd = cwd or os.getcwd()
        self._env = env or {}
        self._initialized = False

    # ── Subclass API ──────────────────────────────────────────────────────

    @property
    @abstractmethod
    def shell_type(self) -> str:
        """Unique identifier: ``powershell``, ``cmd``, ``wsl``, ``bash``."""

    @abstractmethod
    def _build_command_line(self, command: str) -> list[str]:
        """Convert a user command string into the subprocess argv list."""

    @abstractmethod
    def _resolve_executable(self) -> str:
        """Find the shell binary on the current system.  Raises if not found."""

    # ── Optional hooks ────────────────────────────────────────────────────

    def get_init_script(self) -> str:
        """Return a shell-specific init snippet (profile, prompt marker, etc.).
        Override to inject shell-specific setup before each command."""
        return ""

    def get_prompt_marker(self) -> str:
        """Return a string that the shell echoes to mark the end of output.
        Default is empty — no marker.  Override for CWD tracking."""
        return ""

    def validate_command(self, command: str) -> str:
        """Validate and possibly transform a command before execution.
        Returns the (possibly modified) command string.  Raise on invalid."""
        return command

    def wrap_command(self, command: str) -> str:
        """Wrap a command string so it can be executed from the default (bash)
        shell.  The returned string is intended to be passed to ``bash -c``.

        Each backend produces a bash-compatible invocation of its own shell.
        For example, the PS backend returns ``pwsh -Command "Get-Process"``
        and the WSL backend returns ``wsl -d Ubuntu -- bash -c "ps aux"``.

        Subclasses MUST override this to produce the correct invocation.
        The default returns the command unchanged (bash passthrough).
        """
        return command

    def get_env(self) -> dict[str, str]:
        """Return the merged environment for subprocess execution."""
        env = os.environ.copy()
        env.update(self._env)
        return env

    # ── Public API ────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """One-time setup.  Calls _resolve_executable() to validate the shell
        is available.  Subclasses can override for additional setup."""
        if self._initialized:
            return
        self._resolve_executable()
        self._initialized = True

    def run(self, command: str, timeout: int = 30) -> ShellResult:
        """Execute a command in this shell and return the result."""
        import time as _time
        self.initialize()
        command = self.validate_command(command)
        argv = self._build_command_line(command)

        env = self.get_env()
        start = _time.monotonic()

        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._cwd,
                env=env,
            )
            elapsed = (_time.monotonic() - start) * 1000
            return ShellResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                command=command,
                shell_type=self.shell_type,
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (_time.monotonic() - start) * 1000
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                command=command,
                shell_type=self.shell_type,
                duration_ms=elapsed,
            )
        except FileNotFoundError:
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr=f"Shell executable not found for {self.shell_type}",
                command=command,
                shell_type=self.shell_type,
            )
        except Exception as exc:
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                command=command,
                shell_type=self.shell_type,
            )

    def run_piped(self, command: str, input_data: str, timeout: int = 30) -> ShellResult:
        """Execute a command with stdin data piped in."""
        import time as _time
        self.initialize()
        command = self.validate_command(command)
        argv = self._build_command_line(command)
        env = self.get_env()
        start = _time.monotonic()

        try:
            proc = subprocess.run(
                argv,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._cwd,
                env=env,
            )
            elapsed = (_time.monotonic() - start) * 1000
            return ShellResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                command=command,
                shell_type=self.shell_type,
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (_time.monotonic() - start) * 1000
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                command=command,
                shell_type=self.shell_type,
                duration_ms=elapsed,
            )
        except Exception as exc:
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                command=command,
                shell_type=self.shell_type,
            )

    def is_available(self) -> bool:
        """Check whether this shell is available on the current system."""
        try:
            self._resolve_executable()
            return True
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"<{type(self).__name__}(shell_type={self.shell_type!r})>"
