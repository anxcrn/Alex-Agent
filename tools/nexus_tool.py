"""Nexus tool module for managing autonomous self-evolution.

Provides a unified 'nexus' tool to query daemon status, trigger immediate scans,
pause/resume auto-evolution, view learning reports, and execute rollbacks.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


def nexus_tool(
    action: str,
    evolution_id: Optional[str] = None,
    rollback_token: Optional[str] = None,
    limit: int = 10,
    **kwargs: Any
) -> str:
    """Manage the autonomous self-evolution Nexus engine.

    Args:
        action: The management action: 'status', 'scan_now', 'pause', 'resume', 'report', 'rollback'.
        evolution_id: Optional UUID of specific evolution to generate report for.
        rollback_token: Optional UUID/token for rolling back changes.
        limit: Max number of history items to show in status/report.

    Returns:
        Markdown-formatted string summarizing action results.
    """
    try:
        from nexus.daemon import NexusDaemon
        from nexus.config import load_config, save_config
        from nexus.knowledge_base import KnowledgeBase
        from nexus.changelog import Changelog
        from nexus.pipeline import EvolutionPipeline
        from nexus.evolver.reporter import EvolutionReporter
        from nexus.evolver.rollback import RollbackManager
    except ImportError as e:
        return tool_error(f"Nexus module not installed or imports failed: {e}")

    kb = KnowledgeBase()
    changelog = Changelog()
    daemon = NexusDaemon(kb, changelog)
    reporter = EvolutionReporter(kb, changelog)

    # 1. Action: status
    if action == "status":
        daemon_running = daemon.is_running()
        config = load_config()
        stats = kb.get_stats()
        
        status_md = [
            "### 🧬 Alex Agent Nexus status",
            f"- **State**: `{'ACTIVE' if daemon_running else 'INACTIVE'}`",
            f"- **Autonomy Mode**: `{config.mode}`",
            f"- **Enabled**: `{config.enabled}`",
            f"- **Kill Switch Active**: `{config.safety.kill_switch}`",
            f"- **Scan Interval**: `{config.scan_interval_minutes} minutes`",
            "",
            "#### 📊 Knowledge Base Stats",
            f"- Discoveries found: **{stats.get('discoveries', 0)}**",
            f"- Knowledge items extracted: **{stats.get('knowledge', 0)}**",
            f"- MCP Servers found: **{stats.get('mcps', 0)}**",
            f"- Evolutions applied: **{stats.get('evolutions', 0)}**",
            "",
            "#### 📜 Recent Changelog Entries"
        ]
        
        entries = changelog.get_recent(limit)
        if entries:
            for entry in entries:
                status_md.append(
                    f"- [{entry.timestamp[:19]}] **{entry.action.upper()}** - "
                    f"{entry.description} (Confidence: {entry.confidence_score}%)"
                )
        else:
            status_md.append("- No evolution history recorded yet.")
            
        return "\n".join(status_md)

    # 2. Action: scan_now
    elif action == "scan_now":
        config = load_config()
        if config.safety.kill_switch:
            return "❌ Cannot run scan: Kill Switch is active. Resume the engine first."
            
        logger.info("[Nexus/Tool] Manual evolution scan triggered")
        pipeline = EvolutionPipeline(kb, changelog)
        result = pipeline.run_cycle()
        
        res_md = [
            "### 🧬 Evolution Scan Completed",
            f"- Discovered: **{result.discovered}**",
            f"- Deduplicated: **{result.deduplicated}**",
            f"- Analyzed: **{result.analyzed}**",
            f"- Built: **{result.built}**",
            f"- Verified: **{result.verified}**",
            f"- Merged: **{result.merged}**",
            f"- Failed: **{result.failed}**"
        ]
        if result.errors:
            res_md.append("\n#### ⚠️ Errors Encountered:")
            for err in result.errors[:5]:
                res_md.append(f"- {err}")
        return "\n".join(res_md)

    # 3. Action: pause
    elif action == "pause":
        config = load_config()
        config.safety.kill_switch = True
        save_config(config)
        daemon.stop()
        return "⏸️ Alex Agent auto-evolution paused. Kill switch engaged, daemon stopped."

    # 4. Action: resume
    elif action == "resume":
        config = load_config()
        config.safety.kill_switch = False
        save_config(config)
        daemon.start()
        return "▶️ Alex Agent auto-evolution resumed. Kill switch disengaged, daemon started."

    # 5. Action: report
    elif action == "report":
        if evolution_id:
            return reporter.evolution_report(evolution_id)
        else:
            return reporter.daily_digest()

    # 6. Action: rollback
    elif action == "rollback":
        manager = RollbackManager(changelog)
        if rollback_token:
            res = manager.rollback(rollback_token)
        else:
            # Rollback the very last evolution
            results = manager.rollback_last(1)
            res = results[0] if results else None
            
        if not res:
            return "⚠️ No rollback points found or specified."
            
        if res.success:
            files_list = ", ".join(res.files_restored)
            return f"✅ Rollback successful. Restored files: {files_list}"
        else:
            return f"❌ Rollback failed: {res.error}"

    else:
        return tool_error(f"Unknown action: {action}")


def check_nexus_requirements() -> bool:
    """Nexus requires SQLite support."""
    try:
        import sqlite3
        return True
    except ImportError:
        return False


NEXUS_SCHEMA = {
    "name": "nexus",
    "description": (
        "Control and query the autonomous self-evolution Nexus engine. "
        "Allows checking learning status, manually triggering a scan cycle, "
        "pausing/resuming, and rolling back changes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "scan_now", "pause", "resume", "report", "rollback"],
                "description": "The action to perform: check status, force scan, pause, resume, view digest, or rollback changes."
            },
            "evolution_id": {
                "type": "string",
                "description": "Optional UUID of specific evolution to generate report for."
            },
            "rollback_token": {
                "type": "string",
                "description": "Optional UUID token to rollback to a specific checkpoint."
            },
            "limit": {
                "type": "integer",
                "description": "Max history entries to show in status.",
                "default": 10
            }
        },
        "required": ["action"]
    }
}

# Register the tool
registry.register(
    name="nexus",
    toolset="nexus",
    schema=NEXUS_SCHEMA,
    handler=lambda args, **kw: nexus_tool(
        action=args.get("action"),
        evolution_id=args.get("evolution_id"),
        rollback_token=args.get("rollback_token"),
        limit=args.get("limit", 10)
    ),
    check_fn=check_nexus_requirements,
    emoji="🧬",
)
