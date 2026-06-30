"""Rollback manager for Project Nexus.

Allows undoing recent self-evolution codebase modifications using backup copies
associated with changelog rollback tokens.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from alex_constants import get_alex_home
from nexus.changelog import Changelog
from nexus.evolver.code_writer import CodeWriter

logger = logging.getLogger(__name__)


@dataclass
class RollbackResult:
    """Outcome of rolling back an evolution step."""
    success: bool
    files_restored: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class RollbackPoint:
    """A single rollback point description."""
    token: str
    timestamp: str
    description: str
    files_affected: List[str]


class RollbackManager:
    """Manages system state restoration by rolling back files using backups."""

    def __init__(self, changelog: Optional[Changelog] = None) -> None:
        self.changelog = changelog or Changelog()
        self.writer = CodeWriter()

    def rollback(self, rollback_token: str) -> RollbackResult:
        """Rollback modifications matching the specific rollback token."""
        entries = self.changelog.get_entries()
        
        # Find entry with token
        target_entry = None
        for entry in entries:
            if entry.rollback_token == rollback_token:
                target_entry = entry
                break
                
        if not target_entry:
            return RollbackResult(success=False, error=f"Rollback token {rollback_token} not found in changelog")
            
        restored = []
        # Find backup from evolutions or config path
        file_path = target_entry.file_path
        if not file_path:
            return RollbackResult(success=False, error="No file path associated with this rollback token")
            
        # Try to locate backup directory matching token in ~/.alex/nexus/backups
        backup_dir = get_alex_home() / "nexus" / "backups"
        backup_path = ""
        
        # Check folders under backups directory
        for p in backup_dir.glob("*"):
            # Check if name contains our token or timestamp
            if p.is_dir() and target_entry.timestamp[:10].replace("-", "") in p.name:
                backup_path = str(p / Path(file_path).name) if not p.joinpath(Path(file_path).name).is_dir() else str(p)
                break
                
        if not backup_path:
            # Fallback: check if we can restore from general directory
            return RollbackResult(success=False, error="Could not locate backup files for this token")
            
        success = self.writer.restore(backup_path, file_path)
        if success:
            restored.append(file_path)
            
            # Log rollback to changelog
            self.changelog.append(
                action="rolled_back",
                source_url=target_entry.source_url,
                source_type=target_entry.source_type,
                description=f"Rolled back evolution change: {target_entry.description}"
            )
            return RollbackResult(success=True, files_restored=restored)
        else:
            return RollbackResult(success=False, error=f"Restoration failed for file: {file_path}")

    def rollback_last(self, n: int = 1) -> List[RollbackResult]:
        """Rollback the last N changes."""
        entries = self.changelog.get_entries()
        rollback_entries = [e for e in entries if e.rollback_token]
        rollback_entries.reverse()  # Start from newest
        
        results = []
        for e in rollback_entries[:n]:
            res = self.rollback(e.rollback_token)
            results.append(res)
        return results

    def list_rollback_points(self) -> List[RollbackPoint]:
        """List all available points where evolution can be undone."""
        entries = self.changelog.get_entries()
        points = []
        for e in entries:
            if e.rollback_token and e.file_path:
                points.append(RollbackPoint(
                    token=e.rollback_token,
                    timestamp=e.timestamp,
                    description=e.description,
                    files_affected=[e.file_path]
                ))
        return points
