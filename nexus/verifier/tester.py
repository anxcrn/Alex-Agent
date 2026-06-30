"""Evolution tester for Project Nexus.

Validates that newly built tools, skills, and MCP configurations compile and run.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexus.verifier.sandbox import Sandbox

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Outcome of verification testing."""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: str = ""


class EvolutionTester:
    """Tests generated skills, tools, and MCP servers before they can be merged."""

    def __init__(self) -> None:
        self.sandbox = Sandbox()

    def test_skill(self, skill_path: str) -> TestResult:
        """Validate a generated skill directory and SKILL.md file."""
        errors: List[str] = []
        path = Path(skill_path)
        
        md_file = path / "SKILL.md"
        if not md_file.exists():
            errors.append("SKILL.md does not exist in staging directory")
            return TestResult(passed=False, errors=errors)
            
        try:
            content = md_file.read_text(encoding="utf-8")
            # Basic validation of YAML frontmatter
            if not content.startswith("---"):
                errors.append("SKILL.md is missing YAML frontmatter block")
            else:
                parts = content.split("---", 2)
                if len(parts) < 3:
                    errors.append("SKILL.md YAML frontmatter is not closed")
                else:
                    frontmatter = parts[1]
                    if "name:" not in frontmatter:
                        errors.append("YAML frontmatter missing required 'name' field")
                    if "description:" not in frontmatter:
                        errors.append("YAML frontmatter missing required 'description' field")
        except Exception as e:
            errors.append(f"Failed to read SKILL.md: {e}")
            
        passed = len(errors) == 0
        return TestResult(passed=passed, errors=errors, details="Skill frontmatter checks passed")

    def test_tool(self, tool_path: str) -> TestResult:
        """Validate a generated tool by running it in the sandbox."""
        errors: List[str] = []
        
        # Test basic loading and registry import in sandbox
        test_wrapper = (
            f"import sys\n"
            f"sys.path.insert(0, 'd:/Nexus/alex-agent-main')\n"
            f"try:\n"
            f"    # Load the tool module from path\n"
            f"    import importlib.util\n"
            f"    spec = importlib.util.spec_from_file_location('tool_module', r'{tool_path}')\n"
            f"    module = importlib.util.module_from_spec(spec)\n"
            f"    spec.loader.exec_module(module)\n"
            f"    print('SUCCESS')\n"
            f"except Exception as e:\n"
            f"    print('ERROR:', e)\n"
            f"    sys.exit(1)\n"
        )
        
        res = self.sandbox.execute(test_wrapper)
        if res.exit_code != 0:
            errors.append(f"Sandbox tool load failed (Exit Code {res.exit_code}): {res.stderr or res.stdout}")
        elif "SUCCESS" not in res.stdout:
            errors.append(f"Tool execution returned: {res.stdout}")
            
        passed = len(errors) == 0
        return TestResult(passed=passed, errors=errors, details=res.stdout)

    def test_mcp(self, config: Dict[str, Any]) -> TestResult:
        """Basic verification checks on generated MCP config structures."""
        errors: List[str] = []
        
        if not config.get("command"):
            errors.append("MCP config missing command executable")
        if not isinstance(config.get("args"), list):
            errors.append("MCP config args must be a list")
            
        passed = len(errors) == 0
        return TestResult(passed=passed, errors=errors, details="MCP config structure verified")
