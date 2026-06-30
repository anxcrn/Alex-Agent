"""Background daemon manager for Project Nexus.

Runs a background thread that periodically triggers the evolution pipeline
according to configured intervals, respecting safety levers and kill switches.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home
from nexus.config import load_config
from nexus.knowledge_base import KnowledgeBase
from nexus.changelog import Changelog
from nexus.pipeline import EvolutionPipeline

logger = logging.getLogger(__name__)


class NexusDaemon:
    """Manages the background execution of the self-evolution loop."""

    def __init__(self, kb: Optional[KnowledgeBase] = None, changelog: Optional[Changelog] = None) -> None:
        """Initialize the daemon.

        Args:
            kb: Optional KnowledgeBase instance.
            changelog: Optional Changelog instance.
        """
        self.kb = kb or KnowledgeBase()
        self.changelog = changelog or Changelog()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Paths
        self._nexus_dir = get_hermes_home() / "nexus"
        self._nexus_dir.mkdir(parents=True, exist_ok=True)
        self._pid_path = self._nexus_dir / "daemon.pid"
        self._status_path = self._nexus_dir / "daemon_status.json"

    def start(self) -> bool:
        """Start the background daemon thread.

        Returns:
            True if started, False if already running.
        """
        with self._lock:
            if self.is_running():
                logger.info("[Nexus/Daemon] Daemon is already running")
                return False

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._daemon_loop,
                name="nexus_daemon",
                daemon=True
            )
            self._write_pid()
            self._update_status("running")
            self._thread.start()
            logger.info("[Nexus/Daemon] Background daemon started successfully")
            return True

    def stop(self) -> bool:
        """Gracefully stop the background daemon thread.

        Returns:
            True if stopped, False if not running.
        """
        with self._lock:
            if not self.is_running():
                logger.info("[Nexus/Daemon] Daemon is not running")
                return False

            logger.info("[Nexus/Daemon] Stopping background daemon...")
            self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=10.0)
                self._thread = None
            self._clear_pid()
            self._update_status("stopped")
            logger.info("[Nexus/Daemon] Daemon stopped")
            return True

    def is_running(self) -> bool:
        """Check if the daemon thread is alive and PID matches this process."""
        if self._thread and self._thread.is_alive():
            return True

        # Check PID file
        if self._pid_path.exists():
            try:
                pid = int(self._pid_path.read_text().strip())
                # Check if process is running
                import psutil
                if psutil.pid_exists(pid):
                    # Check if it's actually python process
                    proc = psutil.Process(pid)
                    if "python" in proc.name().lower():
                        return True
            except Exception:
                pass
        return False

    def _daemon_loop(self) -> None:
        """Main loop executing on the daemon thread."""
        last_scan_time = 0.0
        
        # Force immediate check on startup (after a brief warm-up)
        time.sleep(5.0)

        while not self._stop_event.is_set():
            try:
                config = load_config()
                if not config.enabled:
                    logger.debug("[Nexus/Daemon] Nexus is disabled in config; sleeping")
                    self._update_status("disabled")
                    self._stop_event.wait(60.0)
                    continue

                if config.safety.kill_switch:
                    logger.warning("[Nexus/Daemon] Kill switch is active! Pausing evolution.")
                    self._update_status("paused_kill_switch")
                    self._stop_event.wait(60.0)
                    continue

                self._update_status("running")
                now = time.monotonic()
                interval_secs = config.scan_interval_minutes * 60.0

                if now - last_scan_time >= interval_secs:
                    logger.info("[Nexus/Daemon] Triggering scheduled evolution cycle...")
                    self._update_status("scanning")
                    
                    pipeline = EvolutionPipeline(self.kb, self.changelog)
                    result = pipeline.run_cycle()
                    
                    last_scan_time = time.monotonic()
                    logger.info("[Nexus/Daemon] Scan cycle complete. Merged: %d, Failed: %d", 
                                result.merged, result.failed)
                    
                    # Log state update
                    self._update_status("running", {
                        "last_scan_at": datetime.now(timezone.utc).isoformat(),
                        "last_results": {
                            "discovered": result.discovered,
                            "merged": result.merged,
                            "failed": result.failed
                        }
                    })

            except Exception as e:
                logger.error("[Nexus/Daemon] Unhandled error in daemon loop: %s", e, exc_info=True)
                self._update_status("error", {"last_error": str(e)})

            # Tick every 10 seconds to respond quickly to stop requests
            self._stop_event.wait(10.0)

    def _write_pid(self) -> None:
        """Write current PID to file."""
        try:
            self._pid_path.write_text(str(os.getpid()))
        except Exception as e:
            logger.warning("[Nexus/Daemon] Failed to write PID file: %s", e)

    def _clear_pid(self) -> None:
        """Delete PID file."""
        try:
            if self._pid_path.exists():
                self._pid_path.unlink()
        except Exception as e:
            logger.warning("[Nexus/Daemon] Failed to clear PID file: %s", e)

    def _update_status(self, state: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Write status JSON file for external commands to query."""
        status = {
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid() if state == "running" else None
        }
        if extra:
            status.update(extra)
        try:
            temp_path = self._status_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(status, indent=2))
            temp_path.replace(self._status_path)
        except Exception as e:
            logger.warning("[Nexus/Daemon] Failed to update status file: %s", e)
