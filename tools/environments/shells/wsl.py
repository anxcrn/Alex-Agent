"""WSL (Windows Subsystem for Linux) execution environment.

Runs Linux commands inside a WSL distro via ``wsl.exe --distribution <distro>``.
Bridges the Windows filesystem through ``/mnt/<drive>/`` paths.

Only available on Windows 10+ with WSL installed.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.environments.shell_base import ShellEnvironment

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"

_WSL_DISTRO_CACHE: list[dict[str, str]] | None = None


class WslEnvironment(ShellEnvironment):
    """Command execution inside a WSL Linux distro.

    Translates Windows paths to WSL paths (``C:\\Users\\x`` → ``/mnt/c/Users/x``)
    so the agent can seamlessly use Linux tools on Windows.
    """

    def __init__(self, cwd: str = "", env: dict[str, str] | None = None, distro: str = ""):
        super().__init__(cwd=cwd, env=env)
        self._distro = distro or ""  # empty = default WSL distro
        self._wsl_exe = ""
        self._distro_info: dict[str, Any] = {}

    @property
    def shell_type(self) -> str:
        return "wsl"

    # ── Distro detection ──────────────────────────────────────────────────

    @staticmethod
    def list_distros() -> list[dict[str, str]]:
        """List installed WSL distros via ``wsl -l -v``.

        Returns list of ``{"name": "...", "state": "...", "version": "..."}``.
        """
        global _WSL_DISTRO_CACHE
        if _WSL_DISTRO_CACHE is not None:
            return _WSL_DISTRO_CACHE

        if not _IS_WINDOWS:
            _WSL_DISTRO_CACHE = []
            return []

        wsl = shutil.which("wsl") or shutil.which("wsl.exe")
        if not wsl:
            _WSL_DISTRO_CACHE = []
            return []

        try:
            result = subprocess.run(
                [wsl, "-l", "-v"],
                capture_output=True, text=True, timeout=15,
            )
            lines = result.stdout.strip().split("\n")
            # Skip header line
            distros = []
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) >= 3:
                    distros.append({
                        "name": parts[0].strip("*").strip(),
                        "state": parts[1],
                        "version": parts[2],
                    })
            _WSL_DISTRO_CACHE = distros
            return distros
        except Exception as exc:
            logger.debug("Failed to list WSL distros: %s", exc)
            _WSL_DISTRO_CACHE = []
            return []

    def get_running_distros(self) -> list[str]:
        """Get all currently running WSL distros."""
        return [d["name"] for d in self.list_distros() if d.get("state", "").lower() == "running"]

    # ── ShellEnvironment implementation ───────────────────────────────────

    def _resolve_executable(self) -> str:
        """Find the WSL launcher (``wsl.exe``)."""
        if not _IS_WINDOWS:
            raise RuntimeError("WSL is only available on Windows 10+")

        custom = os.environ.get("ALEX_WSL_PATH")
        if custom:
            if os.path.isfile(custom):
                return custom
            raise RuntimeError(f"ALEX_WSL_PATH set but not found: {custom}")

        found = shutil.which("wsl") or shutil.which("wsl.exe")
        if found:
            return found

        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        for candidate in (
            os.path.join(sysroot, "System32", "wsl.exe"),
            os.path.join(sysroot, "SysWOW64", "wsl.exe"),
        ):
            if os.path.isfile(candidate):
                return candidate

        raise RuntimeError(
            "WSL not found. Install WSL with: wsl --install\n"
            "See https://learn.microsoft.com/en-us/windows/wsl/install"
        )

    def _build_command_line(self, command: str) -> list[str]:
        exe = self._resolve_executable()
        argv = [exe]
        if self._distro:
            argv.extend(["--distribution", self._distro])
        # Use bash inside WSL (avoids shell selection quirks)
        argv.extend(["--exec", "/bin/bash", "-c", "--"])
        argv.append(f"cd '{self._wsl_path(self._cwd)}' && {command}")
        return argv

    def _wsl_path(self, win_path: str) -> str:
        """Convert a Windows path to a WSL path (e.g. C:\\Users\\x → /mnt/c/Users/x).

        If the path is already a POSIX-style path, return it unchanged.
        """
        if not win_path:
            return "/root"
        if win_path.startswith("/"):
            return win_path

        drive = win_path[0].lower()
        rest = win_path[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"

    def validate_command(self, command: str) -> str:
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")
        return command.strip()

    def wrap_command(self, command: str) -> str:
        exe = self._resolve_executable()
        argv = [exe]
        if self._distro:
            argv.extend(["--distribution", self._distro])
        argv.extend(["--exec", "/bin/bash", "-c", "--"])
        argv.append(f"cd '{self._wsl_path(self._cwd)}' && {command}")
        return shlex.join(argv)

    def get_env(self) -> dict[str, str]:
        """WSL inherits the Windows environment plus any overrides."""
        env = os.environ.copy()
        env.update(self._env)
        # Disable WSL interop warnings, set default to non-interactive
        env.setdefault("WSLENV", "")
        env.setdefault("BASH_ENV", "")
        return env

    def get_init_script(self) -> str:
        """No special init needed for WSL bash."""
        return ""

    def translate_path_to_wsl(self, win_path: str) -> str:
        """Public helper: convert a Windows path to WSL path for agent use."""
        return self._wsl_path(win_path)

    def translate_path_to_windows(self, wsl_path: str) -> str:
        """Public helper: convert a WSL path back to a Windows path."""
        if not wsl_path.startswith("/mnt/"):
            return wsl_path
        parts = wsl_path.split("/")
        drive = parts[2].upper()
        rest = "/".join(parts[3:])
        return f"{drive}:\\{rest.replace('/', '\\')}"

    def get_wsl_version(self) -> str:
        """Return the WSL version info."""
        if not _IS_WINDOWS:
            return "N/A (not Windows)"
        try:
            exe = self._resolve_executable()
            result = subprocess.run(
                [exe, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() or result.stderr.strip() or "unknown"
        except Exception:
            return "unknown"

    def is_available(self) -> bool:
        if not _IS_WINDOWS:
            return False
        try:
            exe = self._resolve_executable()
            return bool(self.list_distros())
        except Exception:
            return False

    def __repr__(self) -> str:
        distro = self._distro or "default"
        return f"<WslEnvironment(distro={distro!r})>"
