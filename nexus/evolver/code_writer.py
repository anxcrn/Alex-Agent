"""Code writer for Project Nexus.

Handles safe, atomic filesystem modification and automatic file backup creation.
"""

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from alex_constants import get_alex_home

logger = logging.getLogger(__name__)


@dataclass
class WriteResult:
    """Outcome of writing an evolution change to disk."""
    success: bool
    file_path: str
    backup_path: Optional[str] = None
    error: Optional[str] = None


class CodeWriter:
    """Safely writes files and directories into the codebase with backup safeguards."""

    def __init__(self) -> None:
        self._nexus_home = get_alex_home() / "nexus"
        self._backup_dir = self._nexus_home / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def write_skill(self, skill_name: str, staging_path: str, category: str = "software-development") -> WriteResult:
        """Copy a generated skill directory to the skills tree."""
        dest_dir = Path("d:/Nexus/alex-agent-main/skills") / category / skill_name
        
        # Check if backup is needed (directory already exists)
        backup_path = None
        if dest_dir.exists():
            backup_path = self._backup_entity(dest_dir, skill_name)
            
        try:
            dest_dir.parent.mkdir(parents=True, exist_ok=True)
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(staging_path, dest_dir)
            logger.info("[Nexus/CodeWriter] Skill written: %s", dest_dir)
            return WriteResult(success=True, file_path=str(dest_dir), backup_path=backup_path)
        except Exception as e:
            logger.error("[Nexus/CodeWriter] Failed to copy skill: %s", e)
            if backup_path:
                self.restore(backup_path, str(dest_dir))
            return WriteResult(success=False, file_path=str(dest_dir), error=str(e))

    def write_tool(self, tool_name: str, staging_path: str) -> WriteResult:
        """Copy a generated tool python file to the tools directory."""
        dest_file = Path("d:/Nexus/alex-agent-main/tools") / f"{tool_name}.py"
        
        # Check if backup is needed
        backup_path = None
        if dest_file.exists():
            backup_path = self._backup_entity(dest_file, tool_name)
            
        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Atomic write
            temp_path = dest_file.with_suffix(".tmp")
            shutil.copy2(staging_path, temp_path)
            temp_path.replace(dest_file)
            
            logger.info("[Nexus/CodeWriter] Tool written: %s", dest_file)
            return WriteResult(success=True, file_path=str(dest_file), backup_path=backup_path)
        except Exception as e:
            logger.error("[Nexus/CodeWriter] Failed to write tool: %s", e)
            if backup_path:
                self.restore(backup_path, str(dest_file))
            return WriteResult(success=False, file_path=str(dest_file), error=str(e))

    def restore(self, backup_path: str, target_path: str) -> bool:
        """Restore an entity from a backup path to its original location."""
        bp = Path(backup_path)
        tp = Path(target_path)
        
        if not bp.exists():
            return False
            
        try:
            if tp.exists():
                if tp.is_dir():
                    shutil.rmtree(tp)
                else:
                    tp.unlink()
                    
            if bp.is_dir():
                shutil.copytree(bp, tp)
            else:
                shutil.copy2(bp, tp)
                
            logger.info("[Nexus/CodeWriter] Restored backup: %s -> %s", bp, tp)
            return True
        except Exception as e:
            logger.error("[Nexus/CodeWriter] Failed to restore backup: %s", e)
            return False

    def _backup_entity(self, path: Path, entity_name: str) -> str:
        """Copy file or directory to backup folder."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dest = self._backup_dir / f"{entity_name}_{timestamp}"
        
        if path.is_dir():
            shutil.copytree(path, backup_dest)
        else:
            backup_dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_dest / path.name)
            backup_dest = backup_dest / path.name
            
        logger.debug("[Nexus/CodeWriter] Backup created: %s -> %s", path, backup_dest)
        return str(backup_dest)
