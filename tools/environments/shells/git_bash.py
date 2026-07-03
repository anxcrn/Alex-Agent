"""Git Bash execution environment — standard bash on all platforms.

On Windows, this uses Git for Windows' bundled bash (``bash.exe`` from
Git Bash).  On Linux/macOS it uses the system ``bash``.

This is the traditional Alex shell and remains the default on all platforms.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil

from tools.environments.shell_base import ShellEnvironment

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"


class GitBashEnvironment(ShellEnvironment):
    """Command execution via bash (Git Bash on Windows, system bash on POSIX).

    Resolution order on Windows:
      1. ALEX_GIT_BASH_PATH env var
      2. Alex portable Git (``%LOCALAPPDATA%\\alex\\git\\bin\\bash.exe``)
      3. Alex portable Git legacy (``%LOCALAPPDATA%\\alex\\git\\usr\\bin\\bash.exe``)
      4. ``bash`` on PATH
      5. ``C:\\Program Files\\Git\\bin\\bash.exe``
      6. ``C:\\Program Files (x86)\\Git\\bin\\bash.exe``

    Resolution order on Linux/macOS:
      1. ``bash`` on PATH
      2. ``/usr/bin/bash``
      3. ``/bin/bash``
      4. ``$SHELL``
      5. ``/bin/sh``
    """

    @property
    def shell_type(self) -> str:
        return "bash"

    def _resolve_executable(self) -> str:
        """Find a bash binary."""
        if _IS_WINDOWS:
            return self._find_windows_bash()
        return self._find_posix_bash()

    @staticmethod
    def _find_posix_bash() -> str:
        """Find bash on Linux/macOS."""
        found = (
            shutil.which("bash")
            or ("/usr/bin/bash" if os.path.isfile("/usr/bin/bash") else None)
            or ("/bin/bash" if os.path.isfile("/bin/bash") else None)
            or os.environ.get("SHELL")
            or "/bin/sh"
        )
        if found and os.path.isfile(found):
            return found
        raise RuntimeError("bash not found on this system")

    @staticmethod
    def _find_windows_bash() -> str:
        """Find Git Bash on Windows."""
        custom = os.environ.get("ALEX_GIT_BASH_PATH")
        if custom and os.path.isfile(custom):
            return custom

        local_appdata = os.environ.get("LOCALAPPDATA", "")
        alex_portable_git = os.path.join(local_appdata, "alex", "git") if local_appdata else ""
        if alex_portable_git:
            for candidate in (
                os.path.join(alex_portable_git, "bin", "bash.exe"),
                os.path.join(alex_portable_git, "usr", "bin", "bash.exe"),
            ):
                if os.path.isfile(candidate):
                    return candidate

        found = shutil.which("bash")
        if found:
            return found

        for candidate in (
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Git", "bin", "bash.exe"),
            os.path.join(local_appdata, "Programs", "Git", "bin", "bash.exe") if local_appdata else "",
        ):
            if candidate and os.path.isfile(candidate):
                return candidate

        raise RuntimeError(
            "Git Bash not found. Alex Agent requires Git for Windows on Windows.\n"
            "Install it from: https://git-scm.com/download/win\n"
            "Or set ALEX_GIT_BASH_PATH to your bash.exe location."
        )

    def _build_command_line(self, command: str) -> list[str]:
        exe = self._resolve_executable()
        # Use login shell for profile sourcing, -c for inline command
        return [exe, "-l", "-c", command]

    def validate_command(self, command: str) -> str:
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")
        return command.strip()

    def wrap_command(self, command: str) -> str:
        return command

    def get_init_script(self) -> str:
        """bash init: set strict mode and suppress job control messages."""
        return 'set -euo pipefail'

    def __repr__(self) -> str:
        try:
            exe = self._resolve_executable()
        except Exception:
            exe = "unresolved"
        return f"<GitBashEnvironment(exe={exe!r})>"
