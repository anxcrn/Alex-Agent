"""Evolution reporter for Project Nexus.

Aggregates stats from the SQLite knowledge base and changelog files to generate
markdown summaries of learning activities and codebase updates.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home
from nexus.knowledge_base import KnowledgeBase
from nexus.changelog import Changelog

logger = logging.getLogger(__name__)


class EvolutionReporter:
    """Generates markdown reports detailing self-evolution activities."""

    def __init__(self, kb: Optional[KnowledgeBase] = None, changelog: Optional[Changelog] = None) -> None:
        self.kb = kb or KnowledgeBase()
        self.changelog = changelog or Changelog()
        self._reports_dir = get_hermes_home() / "nexus" / "reports"
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def daily_digest(self) -> str:
        """Generate a summary of self-evolution activities over the last 24 hours."""
        entries = self.changelog.get_entries()
        
        # Filter entries within last 24 hours
        limit_time = datetime.now(timezone.utc) - timedelta(days=1)
        recent_entries = []
        for e in entries:
            try:
                dt = datetime.fromisoformat(e.timestamp)
                if dt >= limit_time:
                    recent_entries.append(e)
            except Exception:
                pass
                
        # Count stats
        merged_count = sum(1 for e in recent_entries if e.action == "merged")
        verified_count = sum(1 for e in recent_entries if e.action == "verified")
        analyzed_count = sum(1 for e in recent_entries if e.action == "analyzed")
        
        digest = [
            "## 🧬 Daily Self-Evolution Digest",
            f"Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            f"Over the last 24 hours, **Alex Agent** has executed self-evolution pipelines:",
            f"- **{analyzed_count}** new discoveries analyzed.",
            f"- **{verified_count}** updates compiled and verified.",
            f"- **{merged_count}** changes merged into the active codebase.",
            "",
            "### 🛠️ Codebase Modifications & Merges"
        ]
        
        merges = [e for e in recent_entries if e.action == "merged"]
        if merges:
            for m in merges:
                digest.append(
                    f"- **Merged**: {m.description}\n"
                    f"  - Source: [{m.source_type.upper()}]({m.source_url})\n"
                    f"  - File path: `{m.file_path}`\n"
                    f"  - Rollback token: `{m.rollback_token}`"
                )
        else:
            digest.append("- No new features or tools merged in the last 24 hours.")
            
        digest_md = "\n".join(digest)
        self.save_report(digest_md, "daily_digest.md")
        return digest_md

    def evolution_report(self, evolution_id: str) -> str:
        """Generate a detailed report for a specific evolution step."""
        entries = self.changelog.get_entries()
        target = None
        for e in entries:
            if e.id == evolution_id or e.rollback_token == evolution_id:
                target = e
                break
                
        if not target:
            return f"Evolution report with ID {evolution_id} not found."
            
        report = [
            f"## 🧬 Evolution Report: {target.id}",
            f"- **Timestamp**: {target.timestamp}",
            f"- **Action**: `{target.action.upper()}`",
            f"- **Source URL**: [{target.source_url}]({target.source_url})",
            f"- **Source Type**: `{target.source_type}`",
            f"- **Confidence Score**: `{target.confidence_score}%`",
            "",
            "### 📝 Description",
            target.description
        ]
        
        if target.file_path:
            report.extend([
                "",
                "### 📁 Files Affected",
                f"- `{target.file_path}`"
            ])
            
        if target.rollback_token:
            report.extend([
                "",
                f"- **Rollback Token**: `{target.rollback_token}`"
            ])
            
        return "\n".join(report)

    def save_report(self, report_content: str, filename: str) -> None:
        """Write report content to reports directory."""
        try:
            report_file = self._reports_dir / filename
            report_file.write_text(report_content, encoding="utf-8")
        except Exception as e:
            logger.warning("[Nexus/Reporter] Failed to save report: %s", e)
