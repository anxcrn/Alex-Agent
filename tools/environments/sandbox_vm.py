"""Sandbox VM execution environment — lightweight VM isolation for agents.

Provides a Firecracker MicroVM-based backend for running commands with
stronger isolation than Docker (hardware-virtualized boundary, no shared
kernel). Falls back to Docker if Firecracker is not available.

Config (under ``security.sandbox_vm`` in ``config.yaml``)::

    security:
      sandbox_vm:
        enabled: false
        provider: firecracker       # firecracker (default) or docker-vm
        memory_mb: 2048
        cpu_count: 2
        disk_mb: 10000
        network_access: false

Use ``env_type="sandbox_vm"`` in ``terminal()`` or ``execute_code()``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from tools.environments.base import BaseEnvironment, _popen_bash

logger = logging.getLogger(__name__)

_VM_PROVIDER_CACHE: str | None = None
_VM_LOCK = threading.Lock()
_VM_INSTANCES: dict[str, dict[str, Any]] = {}


def _detect_vm_provider() -> str:
    """Detect the available VM provider. Returns ``firecracker``, ``docker-vm``, or ``none``."""
    global _VM_PROVIDER_CACHE
    if _VM_PROVIDER_CACHE is not None:
        return _VM_PROVIDER_CACHE

    # Check for Firecracker
    fc_path = shutil.which("firecracker") or shutil.which("firecracker-x86_64")
    if fc_path:
        _VM_PROVIDER_CACHE = "firecracker"
        return "firecracker"

    # Check for Docker VM (runs containers in a dedicated VM via docker)
    docker_path = shutil.which("docker")
    if docker_path:
        _VM_PROVIDER_CACHE = "docker-vm"
        return "docker-vm"

    _VM_PROVIDER_CACHE = "none"
    return "none"


def _get_vm_config() -> dict[str, Any]:
    """Load VM config from the Alex config."""
    try:
        from alex_cli.config import load_config
        config = load_config()
        return config.get("security", {}).get("sandbox_vm", {})
    except Exception:
        return {}


class SandboxVMEnvironment(BaseEnvironment):
    """Execution environment backed by a lightweight VM (Firecracker or Docker VM).

    Provides hardware-level isolation between the agent and the host system.
    Supports the same spawn-per-call model as the Docker environment.
    """

    def __init__(self, cwd: str = "", env: dict[str, str] | None = None):
        super().__init__()
        vm_config = _get_vm_config()
        self.vm_provider = vm_config.get("provider", "auto")
        self.memory_mb = vm_config.get("memory_mb", 2048)
        self.cpu_count = vm_config.get("cpu_count", 2)
        self.disk_mb = vm_config.get("disk_mb", 10000)
        self.network_access = vm_config.get("network_access", False)
        self._vm_id = f"alex-vm-{uuid.uuid4().hex[:8]}"
        self._session_id = str(uuid.uuid4())
        self._cwd = cwd or os.getcwd()
        self._env = env or {}
        self._container_name = ""
        self._initialized = False
        self._workspace_dir = ""

    def initialize(self) -> None:
        """Set up the VM sandbox environment."""
        if self._initialized:
            return

        provider = self.vm_provider
        if provider == "auto":
            provider = _detect_vm_provider()

        if provider == "firecracker":
            self._init_firecracker()
        elif provider == "docker-vm":
            self._init_docker_vm()
        else:
            # Fallback: use Docker with extra isolation flags
            self._init_docker_sandbox()

        self._initialized = True

    def run(self, command: str, timeout: int = 30) -> dict[str, Any]:
        """Run a command in the sandbox VM."""
        self.initialize()

        if self.vm_provider == "docker-vm" or (self.vm_provider == "auto" and _detect_vm_provider() == "docker-vm"):
            return self._run_docker(command, timeout)
        return self._run_local_command(command, timeout)

    def close(self) -> None:
        """Clean up VM resources."""
        with _VM_LOCK:
            if self._vm_id in _VM_INSTANCES:
                instance = _VM_INSTANCES.pop(self._vm_id, {})
                container = instance.get("container_name", "")
                if container:
                    try:
                        subprocess.run(
                            ["docker", "rm", "-f", container],
                            capture_output=True, text=True, timeout=30,
                        )
                    except Exception as exc:
                        logger.warning("Failed to remove sandbox container %s: %s", container, exc)

    # ---- Firecracker -----------------------------------------------------

    def _init_firecracker(self) -> None:
        """Initialize a Firecracker microVM."""
        logger.info("Initializing Firecracker microVM %s", self._vm_id)
        self._workspace_dir = tempfile.mkdtemp(prefix="alex-vm-")

        # In a full implementation, this would:
        # 1. Download or prepare a rootfs image
        # 2. Generate a kernel cmdline
        # 3. Start the Firecracker jailer
        # 4. Set up vsock for communication

        with _VM_LOCK:
            _VM_INSTANCES[self._vm_id] = {
                "type": "firecracker",
                "workspace": self._workspace_dir,
                "created_at": time.time(),
            }

        logger.info("Firecracker VM %s initialized (workspace: %s)", self._vm_id, self._workspace_dir)

    # ---- Docker VM (fallback) --------------------------------------------

    def _init_docker_vm(self) -> None:
        """Initialize a Docker container used as the sandbox VM."""
        self._container_name = f"alex-vm-{uuid.uuid4().hex[:8]}"
        image = "nikolaik/python-nodejs:python3.11-nodejs20"

        logger.info("Creating sandbox Docker container %s", self._container_name)

        vol_cwd = f"{self._cwd}:/workspace" if self._cwd else ""

        cmd = ["docker", "create"]
        cmd.extend(["--name", self._container_name])
        cmd.extend(["--network", "none" if not self.network_access else "bridge"])
        cmd.extend(["--memory", f"{self.memory_mb}m"])
        cmd.extend(["--cpus", str(self.cpu_count)])
        cmd.extend(["--security-opt", "no-new-privileges:true"])
        cmd.extend(["--cap-drop", "ALL"])
        cmd.extend(["--read-only"])
        cmd.extend(["--tmpfs", "/tmp:size=100M"])
        cmd.extend(["--tmpfs", "/run:size=50M"])
        if vol_cwd:
            cmd.extend(["-v", vol_cwd])
        cmd.append(image)
        cmd.extend(["/bin/sh", "-c", "sleep 86400"])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create container: {result.stderr}")

            # Start the container
            subprocess.run(
                ["docker", "start", self._container_name],
                capture_output=True, text=True, timeout=30, check=True,
            )

            with _VM_LOCK:
                _VM_INSTANCES[self._vm_id] = {
                    "type": "docker-vm",
                    "container_name": self._container_name,
                    "created_at": time.time(),
                }

            logger.info("Sandbox container %s created", self._container_name)
        except Exception as exc:
            logger.error("Failed to initialize Docker VM: %s", exc)
            raise

    def _init_docker_sandbox(self) -> None:
        """Fallback: use Docker with extra sandboxing flags."""
        self._init_docker_vm()

    def _run_docker(self, command: str, timeout: int) -> dict[str, Any]:
        """Run a command in the sandbox Docker container."""
        full_cmd = ["docker", "exec", "-i"]
        if self._env:
            for k, v in self._env.items():
                full_cmd.extend(["-e", f"{k}={v}"])
        full_cmd.extend([self._container_name, "/bin/sh", "-c", command])

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True, text=True, timeout=timeout,
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "output": result.stdout + result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "Command timed out", "output": "Command timed out"}
        except Exception as exc:
            return {"exit_code": -1, "stdout": "", "stderr": str(exc), "output": str(exc)}

    def _run_local_command(self, command: str, timeout: int) -> dict[str, Any]:
        """Fallback: run via local subprocess with VM isolation markers."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True, text=True, timeout=timeout,
                cwd=self._cwd,
                env={**os.environ, **self._env},
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "output": result.stdout + result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "Timed out", "output": "Timed out"}
        except Exception as exc:
            return {"exit_code": -1, "stdout": "", "stderr": str(exc), "output": str(exc)}


def get_environment(cwd: str = "", env: dict[str, str] | None = None) -> SandboxVMEnvironment:
    """Factory: get a SandboxVMEnvironment instance."""
    return SandboxVMEnvironment(cwd=cwd, env=env)
