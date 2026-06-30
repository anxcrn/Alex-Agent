"""Evolution merger for Project Nexus.

Integrates new skills, tools, or MCP configurations into the running codebase
and generates rollback tokens.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from alex_constants import get_alex_home
from nexus.evolver.code_writer import CodeWriter

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Outcome of merging an evolution into the active tree."""
    success: bool
    merged_files: List[str] = field(default_factory=list)
    rollback_token: str = ""
    error: Optional[str] = None


class EvolutionMerger:
    """Orchestrates final changes merging, configuration updates, and hot reloads."""

    def __init__(self) -> None:
        self.writer = CodeWriter()
        self._mcp_config_path = get_alex_home() / "mcp_servers.json"

    def merge_skill(self, skill_name: str, staging_path: str) -> MergeResult:
        """Merge a generated skill into the skills tree."""
        rollback_token = str(uuid.uuid4())
        res = self.writer.write_skill(skill_name, staging_path)
        
        if res.success:
            return MergeResult(
                success=True,
                merged_files=[res.file_path],
                rollback_token=rollback_token
            )
        else:
            return MergeResult(success=False, error=res.error)

    def merge_tool(self, tool_name: str, staging_path: str) -> MergeResult:
        """Merge a generated tool file into the tools folder."""
        rollback_token = str(uuid.uuid4())
        res = self.writer.write_tool(tool_name, staging_path)
        
        if res.success:
            # Hot register in running registry if imported successfully
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("tool_module", res.file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                logger.info("[Nexus/Merger] Hot-loaded tool module: %s", tool_name)
            except Exception as e:
                logger.warning("[Nexus/Merger] Could not hot-load tool %s: %s", tool_name, e)
                
            return MergeResult(
                success=True,
                merged_files=[res.file_path],
                rollback_token=rollback_token
            )
        else:
            return MergeResult(success=False, error=res.error)

    def merge_mcp(self, server_name: str, config: Dict[str, Any]) -> MergeResult:
        """Merge a new MCP server configuration into the home config file."""
        rollback_token = str(uuid.uuid4())
        
        # Load existing config
        mcp_config = {}
        if self._mcp_config_path.exists():
            try:
                mcp_config = json.loads(self._mcp_config_path.read_text())
            except Exception:
                pass
                
        # Backup config file
        backup_path = None
        if self._mcp_config_path.exists():
            backup_path = self.writer._backup_entity(self._mcp_config_path, "mcp_servers")
            
        mcp_config.setdefault("mcpServers", {})[server_name] = config
        
        try:
            temp_path = self._mcp_config_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(mcp_config, indent=2))
            temp_path.replace(self._mcp_config_path)
            
            logger.info("[Nexus/Merger] MCP config merged: %s", server_name)
            return MergeResult(
                success=True,
                merged_files=[str(self._mcp_config_path)],
                rollback_token=rollback_token
            )
        except Exception as e:
            logger.error("[Nexus/Merger] Failed to merge MCP: %s", e)
            if backup_path:
                self.writer.restore(backup_path, str(self._mcp_config_path))
            return MergeResult(success=False, error=str(e))
