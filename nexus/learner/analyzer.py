"""Knowledge analyzer for Project Nexus.

Analyzes raw discoveries using LLM calls to extract structured knowledge
and assess relevance and actionability.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import Discovery

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Structured analysis of a raw discovery."""
    what_is_it: str              # 'skill', 'tool', 'mcp_server', 'technique', 'api', 'library'
    what_does_it_do: str         # Summary of capability
    how_to_use: str              # Install or configuration description
    relevance_to_hermes: float   # 0.0 to 10.0 relevance score
    actionable: bool             # Can we build this automatically?
    actionable_items: List[str] = field(default_factory=list)


class KnowledgeAnalyzer:
    """Analyzes raw crawl discoveries to extract structured AI-actionable knowledge."""

    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("HERMES_LLM_API_KEY")

    def analyze(self, discovery: Discovery) -> AnalysisResult:
        """Analyze a discovery to determine relevance, type, and usage instructions."""
        # Fall back to heuristic keyword-based analysis if no LLM key is configured
        if not self.api_key:
            return self._heuristic_analyze(discovery)
            
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            prompt = (
                f"You are the self-evolution engine analyzer for Alex Agent (an advanced AI developer agent).\n"
                f"Analyze the following discovery:\n"
                f"Title: {discovery.title}\n"
                f"Source URL: {discovery.source_url}\n"
                f"Content Snippet: {discovery.content[:3000]}\n\n"
                f"Extract structured information as a JSON object with the following keys:\n"
                f"- what_is_it: one of 'skill', 'tool', 'mcp_server', 'technique', 'api', 'library'\n"
                f"- what_does_it_do: brief description of functionality\n"
                f"- how_to_use: code snippets, shell commands or configs required to use it\n"
                f"- relevance_to_hermes: score from 0.0 to 10.0 (how useful is this for an AI coder agent?)\n"
                f"- actionable: boolean (can we auto-generate a Python tool, SKILL.md or MCP config for this?)\n"
                f"- actionable_items: list of files to modify/add or commands to run\n"
                f"Respond ONLY with valid JSON."
            )
            
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            res_dict = {}
            import json
            if resp.choices and resp.choices[0].message.content:
                res_dict = json.loads(resp.choices[0].message.content)
                
            return AnalysisResult(
                what_is_it=str(res_dict.get("what_is_it", "technique")),
                what_does_it_do=str(res_dict.get("what_does_it_do", "")),
                how_to_use=str(res_dict.get("how_to_use", "")),
                relevance_to_hermes=float(res_dict.get("relevance_to_hermes", 5.0)),
                actionable=bool(res_dict.get("actionable", False)),
                actionable_items=list(res_dict.get("actionable_items", []))
            )
        except Exception as e:
            logger.warning("[Nexus/Analyzer] LLM analysis failed, falling back to heuristics: %s", e)
            return self._heuristic_analyze(discovery)

    def _heuristic_analyze(self, discovery: Discovery) -> AnalysisResult:
        """Fallback rule-based heuristic analyzer when LLM is unavailable."""
        title_lower = discovery.title.lower()
        content_lower = discovery.content.lower()
        
        # 1. Type determination
        what_is_it = "technique"
        actionable = False
        actionable_items = []
        
        if "mcp" in title_lower or "modelcontextprotocol" in content_lower:
            what_is_it = "mcp_server"
            actionable = True
            actionable_items = ["install_mcp"]
        elif "tool" in title_lower or "api" in title_lower:
            what_is_it = "tool"
            actionable = True
            actionable_items = ["create_tool"]
        elif "skill" in title_lower or "guide" in title_lower:
            what_is_it = "skill"
            actionable = True
            actionable_items = ["create_skill"]
            
        # 2. Relevance calculation
        relevance = 5.0
        if "agent" in content_lower or "mcp" in content_lower:
            relevance += 2.0
        if "github" in discovery.source_url:
            relevance += 1.0
            
        relevance = min(10.0, relevance)
        
        return AnalysisResult(
            what_is_it=what_is_it,
            what_does_it_do=f"Discovered {discovery.title}. Appears to be a {what_is_it}.",
            how_to_use=discovery.content[:1000],
            relevance_to_hermes=relevance,
            actionable=actionable,
            actionable_items=actionable_items
        )
