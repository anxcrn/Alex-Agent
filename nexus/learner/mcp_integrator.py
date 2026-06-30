"""MCP integrator for Project Nexus.

Discovers installation methods for new MCP servers and creates configuration files in staging.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from alex_constants import get_alex_home
from nexus.crawlers.base import Discovery

logger = logging.getLogger(__name__)


@dataclass
class MCPIntegrationResult:
    """Result of generating an MCP server configuration."""
    server_name: str
    install_command: str
    config_entry: Dict[str, Any]
    success: bool
    error: Optional[str] = None


class MCPIntegrator:
    """Auto-discovers and configures external Model Context Protocol servers."""

    def __init__(self) -> None:
        self._staging_dir = get_alex_home() / "nexus" / "staging" / "mcps"
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    def integrate(self, discovery: Discovery) -> MCPIntegrationResult:
        """Analyze MCP server metadata and generate config entries."""
        name = discovery.metadata.get("name", "").strip().lower()
        if not name:
            name = f"mcp-server-{discovery.content_hash[:8]}"
            
        packages = discovery.metadata.get("packages") or []
        install_command = ""
        config_entry: Dict[str, Any] = {}
        
        # Simple heuristic to determine npm/npx vs pip/python
        is_npm = False
        is_python = False
        
        # Check packages info
        for p in packages:
            if isinstance(p, dict):
                p_type = p.get("type", "")
                if p_type == "npm":
                    is_npm = True
                    install_command = f"npx -y {p.get('name')}"
                elif p_type == "pip":
                    is_python = True
                    install_command = f"python -m {p.get('name')}"

        if not install_command:
            # Fallback based on content keywords
            if "npm" in discovery.content or "npx" in discovery.content:
                is_npm = True
                install_command = f"npx -y {name}"
            else:
                is_python = True
                install_command = f"uvx {name}"

        # Generate configuration entry structure
        if is_npm:
            config_entry = {
                "command": "npx",
                "args": ["-y", name],
                "env": {}
            }
        else:
            config_entry = {
                "command": "uvx",
                "args": [name],
                "env": {}
            }

        # Write config JSON entry to staging
        config_file = self._staging_dir / f"{name}.json"
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(json.dumps(config_entry, indent=2))
            logger.info("[Nexus/MCPIntegrator] MCP config generated in staging: %s", config_file)
            return MCPIntegrationResult(
                server_name=name,
                install_command=install_command,
                config_entry=config_entry,
                success=True
            )
        except Exception as e:
            logger.error("[Nexus/MCPIntegrator] Failed to write MCP config: %s", e)
            return MCPIntegrationResult(
                server_name=name,
                install_command=install_command,
                config_entry=config_entry,
                success=False,
                error=str(e)
            )
