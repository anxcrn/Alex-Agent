"""PowerShell execution environment.

Runs commands via ``pwsh`` (PowerShell 7+, cross-platform) with fallback to
``powershell.exe`` (Windows PowerShell 5.1).  Handles ``$PROFILE``,
``$LASTEXITCODE``, and structured output via ``ConvertTo-Json``.

Windows: works natively — no Git Bash or WSL required.
Linux/macOS: works when ``pwsh`` is installed.
"""

from __future__ import annotations

import logging
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

from tools.environments.shell_base import ShellEnvironment

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"


class PowerShellEnvironment(ShellEnvironment):
    """Command execution via PowerShell (pwsh or powershell.exe)."""

    @property
    def shell_type(self) -> str:
        return "powershell"

    def _resolve_executable(self) -> str:
        """Find PowerShell.  Prefer pwsh (v7+), fall back to powershell.exe (v5.1).

        Resolution order:
          1. ALEX_POWERSHELL_PATH env var (explicit override)
          2. ``pwsh`` on PATH  (cross-platform, modern)
          3. ``powershell.exe`` on PATH  (Windows only, legacy)
        """
        custom = os.environ.get("ALEX_POWERSHELL_PATH")
        if custom:
            if os.path.isfile(custom):
                return custom
            raise RuntimeError(f"ALEX_POWERSHELL_PATH set but not found: {custom}")

        found = shutil.which("pwsh")
        if found:
            return found

        if _IS_WINDOWS:
            found = shutil.which("powershell.exe")
            if found:
                return found

            # Common install paths for Windows PowerShell
            for candidate in (
                os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
                os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PowerShell", "7", "pwsh.exe"),
                os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "PowerShell", "7", "pwsh.exe"),
            ):
                if os.path.isfile(candidate):
                    return candidate

        raise RuntimeError(
            "PowerShell not found. Install PowerShell 7+ from:\n"
            "  https://github.com/PowerShell/PowerShell/releases\n"
            "Or set ALEX_POWERSHELL_PATH to your pwsh/powershell.exe location."
        )

    def get_init_script(self) -> str:
        """Return PowerShell-specific init."""
        if self._is_pwsh:
            return "$ProgressPreference = 'SilentlyContinue'; $ErrorActionPreference = 'Stop';"
        return "$ErrorActionPreference = 'Stop'"

    def _resolve_pwsh(self) -> str:
        """Check whether the resolved executable is pwsh (v7+) or powershell.exe."""
        exe = self._resolve_executable()
        return os.path.basename(exe).lower().startswith("pwsh")

    @property
    def _is_pwsh(self) -> bool:
        try:
            return self._resolve_pwsh()
        except Exception:
            return False

    def _build_command_line(self, command: str) -> list[str]:
        exe = self._resolve_executable()
        # Use -NoProfile for speed and isolation, -Command for inline execution
        return [exe, "-NoProfile", "-Command", command]

    def validate_command(self, command: str) -> str:
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")
        return command.strip()

    def wrap_command(self, command: str) -> str:
        exe = self._resolve_executable()
        return shlex.join([exe, "-NoProfile", "-Command", command])

    def run_script(self, script_path: str, args: list[str] | None = None) -> ShellResult:
        """Run a PowerShell script file (.ps1)."""
        from tools.environments.shell_base import ShellResult
        import time as _time

        exe = self._resolve_executable()
        argv = [exe, "-NoProfile", "-File", script_path]
        if args:
            argv.extend(args)

        start = _time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self._cwd,
                env=self.get_env(),
            )
            elapsed = (_time.monotonic() - start) * 1000
            return ShellResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                command=f"pwsh -File {script_path}",
                shell_type="powershell",
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            from tools.environments.shell_base import ShellResult
            elapsed = (_time.monotonic() - start) * 1000
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr="Script timed out after 60s",
                command=f"pwsh -File {script_path}",
                shell_type="powershell",
                duration_ms=elapsed,
            )

    def get_ps_version(self) -> str:
        """Return the PowerShell version string."""
        result = self.run("$PSVersionTable.PSVersion.ToString()")
        return result.stdout.strip() or "unknown"

    def __repr__(self) -> str:
        try:
            exe = self._resolve_executable()
        except Exception:
            exe = "unresolved"
        return f"<PowerShellEnvironment(exe={exe!r})>"
