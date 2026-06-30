"""Skill builder for Project Nexus.

Takes raw discoveries and generates SKILL.md documentation structure in staging.
"""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from hermes_constants import get_hermes_home
from nexus.crawlers.base import Discovery
from nexus.learner.analyzer import AnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class SkillBuildResult:
    """Result of generating a new skill."""
    skill_name: str
    skill_path: str
    files_created: List[str]
    success: bool
    error: Optional[str] = None


class SkillBuilder:
    """Builds user-authorable SKILL.md directories in a staging location."""

    def __init__(self) -> None:
        self._staging_dir = get_hermes_home() / "nexus" / "staging" / "skills"
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("HERMES_LLM_API_KEY")

    def build(self, analysis: AnalysisResult, discovery: Discovery) -> SkillBuildResult:
        """Create documentation structure for a new skill from analysis."""
        # Sanitize skill name
        raw_name = discovery.title.split(":")[-1].strip()
        skill_name = re.sub(r"[^a-zA-Z0-9_-]", "-", raw_name).lower()
        skill_name = re.sub(r"-+", "-", skill_name).strip("-")
        
        if not skill_name:
            skill_name = f"skill-{discovery.content_hash[:8]}"
            
        skill_path = self._staging_dir / skill_name
        skill_path.mkdir(parents=True, exist_ok=True)
        
        md_file = skill_path / "SKILL.md"
        
        # Build skill content
        skill_content = self._generate_skill_md(skill_name, analysis, discovery)
        
        try:
            md_file.write_text(skill_content, encoding="utf-8")
            logger.info("[Nexus/SkillBuilder] Skill generated in staging: %s", md_file)
            return SkillBuildResult(
                skill_name=skill_name,
                skill_path=str(skill_path),
                files_created=[str(md_file)],
                success=True
            )
        except Exception as e:
            logger.error("[Nexus/SkillBuilder] Failed to write skill file: %s", e)
            return SkillBuildResult(
                skill_name=skill_name,
                skill_path=str(skill_path),
                files_created=[],
                success=False,
                error=str(e)
            )

    def _generate_skill_md(self, name: str, analysis: AnalysisResult, discovery: Discovery) -> str:
        """Query LLM or use fallback template to generate SKILL.md body."""
        if self.api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key)
                
                prompt = (
                    f"Create a SKILL.md file for the skill named '{name}'.\n"
                    f"Description of what it does: {analysis.what_does_it_do}\n"
                    f"Instructions: {analysis.how_to_use}\n"
                    f"Source URL: {discovery.source_url}\n\n"
                    f"The SKILL.md file MUST start with a YAML frontmatter block:\n"
                    f"---\n"
                    f"name: {name}\n"
                    f"description: A concise description of the skill.\n"
                    f"---\n\n"
                    f"Followed by a markdown document explaining how to use it, with examples, use cases, and commands."
                )
                
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )
                
                if resp.choices and resp.choices[0].message.content:
                    return resp.choices[0].message.content
            except Exception as e:
                logger.warning("[Nexus/SkillBuilder] LLM generation failed, falling back to template: %s", e)

        # Fallback template
        return (
            f"---\n"
            f"name: {name}\n"
            f"description: {analysis.what_does_it_do[:100]}\n"
            f"---\n\n"
            f"# {name.replace('-', ' ').title()}\n\n"
            f"## Description\n"
            f"{analysis.what_does_it_do}\n\n"
            f"## How to Use\n"
            f"Refer to details from original source: {discovery.source_url}\n\n"
            f"```\n"
            f"{analysis.how_to_use}\n"
            f"```\n"
        )
