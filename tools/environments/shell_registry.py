"""Shell registry — discover, select, and manage shell backends.

Maintains a registry of available ``ShellEnvironment`` implementations and
provides auto-detection of which shells are available on the current system.

Usage::

    from tools.environments.shell_registry import registry as shell_registry

    # Get the default shell for this platform
    shell = shell_registry.get_default()

    # Run a command in PowerShell
    ps = shell_registry.get("powershell")
    result = ps.run("Get-Process | Select-Object -First 5")

    # List all available shells
    for name in shell_registry.available():
        print(name)
"""

from __future__ import annotations

import logging
import os
import platform

from tools.environments.shell_base import ShellEnvironment
from tools.environments.shells.git_bash import GitBashEnvironment
from tools.environments.shells.powershell import PowerShellEnvironment
from tools.environments.shells.cmd import CmdEnvironment
from tools.environments.shells.wsl import WslEnvironment

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"
_DEFAULT_SHELL_CACHE: str | None = None


class ShellRegistry:
    """Registry of available shell backends with auto-detection."""

    def __init__(self) -> None:
        self._registry: dict[str, type[ShellEnvironment]] = {}
        self._instances: dict[str, ShellEnvironment] = {}
        self._availability_cache: dict[str, bool] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all known shell backends."""
        self.register("bash", GitBashEnvironment)
        self.register("powershell", PowerShellEnvironment)
        self.register("cmd", CmdEnvironment)
        self.register("wsl", WslEnvironment)

    def register(self, name: str, shell_cls: type[ShellEnvironment]) -> None:
        """Register a shell backend class under *name*."""
        self._registry[name] = shell_cls
        self._availability_cache.pop(name, None)

    def get(self, name: str, **kwargs) -> ShellEnvironment:
        """Get a shell backend by name.

        Args:
            name: Shell name (``bash``, ``powershell``, ``cmd``, ``wsl``).
            **kwargs: Passed to the shell's constructor.

        Returns:
            A ``ShellEnvironment`` instance.

        Raises:
            KeyError: If the shell is not registered.
            RuntimeError: If the shell is not available on this system.
        """
        cls = self._registry.get(name)
        if cls is None:
            raise KeyError(f"Unknown shell: {name!r}. Available: {list(self._registry.keys())}")

        # Return a cached default instance if no kwargs
        cache_key = name
        if not kwargs:
            cached = self._instances.get(cache_key)
            if cached is not None:
                return cached

        instance = cls(**kwargs)
        if not kwargs:
            self._instances[cache_key] = instance
        return instance

    def available(self) -> list[str]:
        """Return names of all shells available on this system.

        Probes each registered shell once and caches the result.
        """
        available = []
        for name, cls in self._registry.items():
            if name in self._availability_cache:
                if self._availability_cache[name]:
                    available.append(name)
                continue
            try:
                instance = cls()
                is_avail = instance.is_available()
                self._availability_cache[name] = is_avail
                if is_avail:
                    available.append(name)
            except Exception as exc:
                logger.debug("Shell %r not available: %s", name, exc)
                self._availability_cache[name] = False
        return available

    def get_default(self, preferred: str = "") -> ShellEnvironment:
        """Get the default shell for the current platform.

        Args:
            preferred: Preferred shell name from config. If empty or
                unavailable, falls back to platform default.

        Priority on Windows:
            1. Preferred shell (if available)
            2. PowerShell (if available)
            3. Git Bash (legacy fallback)

        Priority on Linux/macOS:
            1. Preferred shell (if available, e.g. zsh)
            2. bash (always available)
        """
        if preferred:
            try:
                shell = self.get(preferred)
                if shell.is_available():
                    return shell
            except (KeyError, RuntimeError):
                pass

        if _IS_WINDOWS:
            for candidate in ("powershell", "bash"):
                try:
                    shell = self.get(candidate)
                    if shell.is_available():
                        return shell
                except (KeyError, RuntimeError):
                    continue
            raise RuntimeError("No shell available on this Windows system")

        # POSIX: bash is always available
        return self.get("bash")

    def get_shell_for_command(self, command: str) -> str:
        """Heuristic: suggest the best shell for a given command string.

        Args:
            command: The command string to analyze.

        Returns:
            Shell name hint (``powershell``, ``cmd``, ``wsl``, ``bash``).
        """
        cmd = command.strip()

        # PowerShell-specific syntax
        if any(cmd.startswith(kw) for kw in (
            "Get-", "Set-", "New-", "Remove-", "Invoke-",
            "Write-", "Out-", "Select-", "Where-", "ForEach-",
        )):
            return "powershell"
        if "$PSVersionTable" in cmd or "ConvertTo-Json" in cmd:
            return "powershell"
        if "-Recurse" in cmd or "-Filter" in cmd or "-Force" in cmd:
            # PowerShell-style flags (could also be bash, but common in PS)
            if "|" in cmd:
                return "powershell"

        # cmd.exe-specific syntax
        if cmd.startswith(("dir", "copy ", "move ", "ren ", "del ", "type ", "echo %")):
            return "cmd"
        if "%ERRORLEVEL%" in cmd or "%CD%" in cmd:
            return "cmd"

        # WSL-specific: Linux-only commands on Windows
        if _IS_WINDOWS:
            wsl_hints = ("apt", "apt-get", "dpkg", "systemctl", "service ",
                         "grep ", "sed ", "awk ", "chmod ", "chown ",
                         "ls /mnt/", "wsl ")
            if any(cmd.startswith(h) for h in wsl_hints):
                return "wsl"

        # Default to bash
        return "bash"

    def __repr__(self) -> str:
        avail = self.available()
        return f"<ShellRegistry(available={avail})>"


# Module-level singleton
registry = ShellRegistry()
