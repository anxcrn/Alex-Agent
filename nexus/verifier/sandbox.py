"""Sandbox execution manager for Project Nexus.

Executes newly generated tools or test suites in an isolated temporary environment.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """Outcome of sandbox code execution."""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_seconds: float


class Sandbox:
    """Provides isolated environment execution for python scripts."""

    def __init__(self) -> None:
        self._temp_dir: Optional[Path] = None

    def execute(self, code: str, timeout: int = 15) -> SandboxResult:
        """Execute a string of python code in the sandbox."""
        with tempfile.TemporaryDirectory(prefix="nexus_sandbox_") as tmpdir:
            temp_path = Path(tmpdir) / "run.py"
            temp_path.write_text(code, encoding="utf-8")
            return self.execute_file(str(temp_path), timeout=timeout)

    def execute_file(self, filepath: str, timeout: int = 15) -> SandboxResult:
        """Run a specific file in the sandbox."""
        start = time.monotonic()
        timed_out = False
        exit_code = -1
        stdout = ""
        stderr = ""
        
        try:
            # Run python subprocess in sandbox
            res = subprocess.run(
                ["python", filepath],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            exit_code = res.returncode
            stdout = res.stdout
            stderr = res.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = e.stdout or ""
            stderr = e.stderr or ""
        except Exception as e:
            stderr = f"Execution setup failed: {e}"
            
        duration = time.monotonic() - start
        
        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            duration_seconds=duration
        )
