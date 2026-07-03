"""Windows Command Prompt (cmd.exe) execution environment.

Runs commands via ``cmd.exe /S /C``.  The classic Windows shell — always
available on Windows, not available on Linux/macOS.  Parses ``%ERRORLEVEL%``
for exit code reporting.
"""

from __future__ import annotations

import logging
import os
import platform
import shlex
import shutil

from tools.environments.shell_base import ShellEnvironment

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"


class CmdEnvironment(ShellEnvironment):
    """Command execution via Windows cmd.exe."""

    @property
    def shell_type(self) -> str:
        return "cmd"

    def _resolve_executable(self) -> str:
        """Find cmd.exe.  Only available on Windows.

        Resolution order:
          1. ALEX_CMD_PATH env var
          2. ``%COMSPEC%`` env var (always set on Windows — defaults to cmd.exe)
          3. ``cmd.exe`` on PATH
          4. Well-known install paths
        """
        if not _IS_WINDOWS:
            raise RuntimeError("cmd.exe is only available on Windows")

        custom = os.environ.get("ALEX_CMD_PATH")
        if custom:
            if os.path.isfile(custom):
                return custom
            raise RuntimeError(f"ALEX_CMD_PATH set but not found: {custom}")

        comspec = os.environ.get("COMSPEC")
        if comspec and os.path.isfile(comspec):
            return comspec

        found = shutil.which("cmd.exe")
        if found:
            return found

        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        for candidate in (
            os.path.join(sysroot, "System32", "cmd.exe"),
            os.path.join(sysroot, "SysWOW64", "cmd.exe"),
        ):
            if os.path.isfile(candidate):
                return candidate

        raise RuntimeError("cmd.exe not found. This should never happen on Windows.")

    def _build_command_line(self, command: str) -> list[str]:
        exe = self._resolve_executable()
        # /D = skip AutoRun (isolated), /S = strip outer quotes, /C = run and exit
        return [exe, "/D", "/S", "/C", command]

    def validate_command(self, command: str) -> str:
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")
        return command.strip()

    def wrap_command(self, command: str) -> str:
        exe = self._resolve_executable()
        return shlex.join([exe, "/D", "/S", "/C", command])

    def get_init_script(self) -> str:
        """cmd.exe init: suppress echo and set strict parsing."""
        return "@echo off"

    def _wrap_errorlevel(self, command: str) -> str:
        """Append ERRORLEVEL reporting so the agent can check exit codes."""
        return f"{command} & echo [EXIT:%ERRORLEVEL%]"

    def run(self, command: str, timeout: int = 30) -> ShellResult:
        """Execute a cmd.exe command and extract the exit code."""
        import re as _re
        import time as _time

        self.initialize()
        command = self.validate_command(command)

        # Wrap with ERRORLEVEL capture
        wrapped = self._wrap_errorlevel(command)
        argv = self._build_command_line(wrapped)
        env = self.get_env()
        start = _time.monotonic()

        try:
            proc = __import__("subprocess", fromlist=["run"]).run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._cwd,
                env=env,
            )
            elapsed = (_time.monotonic() - start) * 1000
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            # Parse ERRORLEVEL from the end of stdout
            exit_code = proc.returncode
            marker_match = _re.search(r'\[EXIT:(\d+)\]', stdout)
            if marker_match:
                exit_code = int(marker_match.group(1))
                stdout = _re.sub(r'\s*\[EXIT:\d+\]\s*$', '', stdout).rstrip()

            from tools.environments.shell_base import ShellResult
            return ShellResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                command=command,
                shell_type="cmd",
                duration_ms=elapsed,
            )
        except __import__("subprocess", fromlist=["TimeoutExpired"]).TimeoutExpired:
            elapsed = (_time.monotonic() - start) * 1000
            from tools.environments.shell_base import ShellResult
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                command=command,
                shell_type="cmd",
                duration_ms=elapsed,
            )
        except Exception as exc:
            from tools.environments.shell_base import ShellResult
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                command=command,
                shell_type="cmd",
            )

    def is_available(self) -> bool:
        """cmd.exe is only available on Windows."""
        if not _IS_WINDOWS:
            return False
        return super().is_available()

    def __repr__(self) -> str:
        try:
            exe = self._resolve_executable()
        except Exception:
            exe = "unresolved"
        return f"<CmdEnvironment(exe={exe!r})>"
