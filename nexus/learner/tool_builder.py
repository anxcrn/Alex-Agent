"""Tool builder for Project Nexus.

Takes raw discoveries and generates executable Python tool modules in staging.
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
class ToolBuildResult:
    """Result of generating a new tool."""
    tool_name: str
    file_path: str
    success: bool
    error: Optional[str] = None


class ToolBuilder:
    """Builds Python tool files registered in staging."""

    def __init__(self) -> None:
        self._staging_dir = get_hermes_home() / "nexus" / "staging" / "tools"
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("HERMES_LLM_API_KEY")

    def build(self, analysis: AnalysisResult, discovery: Discovery) -> ToolBuildResult:
        """Generate executable python file for a tool."""
        # Sanitize tool name
        raw_name = discovery.title.split(":")[-1].strip()
        tool_name = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name).lower()
        tool_name = re.sub(r"_+", "_", tool_name).strip("_")
        
        if not tool_name:
            tool_name = f"tool_{discovery.content_hash[:8]}"
            
        file_path = self._staging_dir / f"{tool_name}.py"
        
        tool_code = self._generate_tool_code(tool_name, analysis, discovery)
        
        try:
            file_path.write_text(tool_code, encoding="utf-8")
            logger.info("[Nexus/ToolBuilder] Tool generated in staging: %s", file_path)
            return ToolBuildResult(
                tool_name=tool_name,
                file_path=str(file_path),
                success=True
            )
        except Exception as e:
            logger.error("[Nexus/ToolBuilder] Failed to write tool file: %s", e)
            return ToolBuildResult(
                tool_name=tool_name,
                file_path=str(file_path),
                success=False,
                error=str(e)
            )

    def _generate_tool_code(self, name: str, analysis: AnalysisResult, discovery: Discovery) -> str:
        """Query LLM or use fallback template to generate tool Python file."""
        if self.api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key)
                
                prompt = (
                    f"Create a python tool module file for a tool named '{name}'.\n"
                    f"Description: {analysis.what_does_it_do}\n"
                    f"Instructions/API snippet: {analysis.how_to_use}\n\n"
                    f"It must strictly follow the registry structure for tools. Example:\n"
                    f"```python\n"
                    f"from tools.registry import registry, tool_error\n"
                    f"import logging\n"
                    f"logger = logging.getLogger(__name__)\n\n"
                    f"def {name}_tool(action, **kwargs):\n"
                    f"    try:\n"
                    f"        # Implementation of tool logic\n"
                    f"        return 'Result'\n"
                    f"    except Exception as e:\n"
                    f"        return tool_error(str(e))\n\n"
                    f"SCHEMA = {{\n"
                    f"    'name': '{name}',\n"
                    f"    'description': '{analysis.what_does_it_do[:100]}',\n"
                    f"    'parameters': {{\n"
                    f"        'type': 'object',\n"
                    f"        'properties': {{\n"
                    f"            'action': {{'type': 'string'}}\n"
                    f"        }},\n"
                    f"        'required': ['action']\n"
                    f"    }}\n"
                    f"}}\n\n"
                    f"registry.register(\n"
                    f"    name='{name}',\n"
                    f"    toolset='nexus-generated',\n"
                    f"    schema=SCHEMA,\n"
                    f"    handler=lambda args, **kw: {name}_tool(**args),\n"
                    f"    emoji='🔧'\n"
                    f")\n"
                    f"```\n"
                    f"Respond ONLY with valid Python code, no markdown block code wrappers."
                )
                
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                
                if resp.choices and resp.choices[0].message.content:
                    code = resp.choices[0].message.content
                    # Strip any markdown wrappers if LLM returned them
                    code = code.replace("```python", "").replace("```", "").strip()
                    return code
            except Exception as e:
                logger.warning("[Nexus/ToolBuilder] LLM code generation failed, falling back: %s", e)

        # Fallback template
        desc_escaped = analysis.what_does_it_do[:150].replace("'", "\\'")
        return (
            f"from tools.registry import registry, tool_error\n"
            f"import logging\n"
            f"logger = logging.getLogger(__name__)\n\n"
            f"def {name}_tool(action: str, **kwargs):\n"
            f"    \"\"\"{analysis.what_does_it_do}\"\"\"\n"
            f"    logger.info('[Nexus] Executed stub tool {name}')\n"
            f"    return f'Stub tool {name} called with action: ' + action\n\n"
            f"SCHEMA = {{\n"
            f"    'name': '{name}',\n"
            f"    'description': '{desc_escaped}',\n"
            f"    'parameters': {{\n"
            f"        'type': 'object',\n"
            f"        'properties': {{\n"
            f"            'action': {{'type': 'string', 'description': 'Action to perform'}}\n"
            f"        }},\n"
            f"        'required': ['action']\n"
            f"    }}\n"
            f"}}\n\n"
            f"registry.register(\n"
            f"    name='{name}',\n"
            f"    toolset='nexus-generated',\n"
            f"    schema=SCHEMA,\n"
            f"    handler=lambda args, **kw: {name}_tool(**args),\n"
            f"    emoji='🔧'\n"
            f")\n"
        )
