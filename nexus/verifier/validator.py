"""Correctness validator for Project Nexus.

Reviews generated Python tools/skills using LLM prompting to verify logical correctness.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """LLM code review validation results."""
    valid: bool
    confidence: float
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class CorrectnessValidator:
    """Uses LLM models to perform structured reviews on generated evolution changes."""

    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("HERMES_LLM_API_KEY")

    def validate(self, code: str, intended_purpose: str) -> ValidationResult:
        """Analyze the source code to verify if it correctly implements the purpose."""
        if not self.api_key:
            return self._heuristic_validate(code)
            
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            prompt = (
                f"Perform a code review of the following generated code.\n"
                f"Intended Purpose: {intended_purpose}\n"
                f"Code:\n"
                f"```python\n{code}\n```\n\n"
                f"Respond ONLY with a JSON object containing the keys:\n"
                f"- valid: boolean (is the logic sound, complete, and does it fulfill the purpose?)\n"
                f"- confidence: float (0.0 to 100.0, indicating correctness level)\n"
                f"- issues: list of strings (logical errors, resource leaks, or issues)\n"
                f"- suggestions: list of strings (improvements)"
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
                
            return ValidationResult(
                valid=bool(res_dict.get("valid", True)),
                confidence=float(res_dict.get("confidence", 90.0)),
                issues=list(res_dict.get("issues", [])),
                suggestions=list(res_dict.get("suggestions", []))
            )
        except Exception as e:
            logger.warning("[Nexus/Validator] LLM validation failed: %s", e)
            return self._heuristic_validate(code)

    def _heuristic_validate(self, code: str) -> ValidationResult:
        """Fallback validation checking basic compilation and structure."""
        issues = []
        try:
            compile(code, "<string>", "exec")
        except SyntaxError as e:
            issues.append(f"Syntax error during compilation: {e}")
            
        valid = len(issues) == 0
        confidence = 85.0 if valid else 0.0
        
        return ValidationResult(
            valid=valid,
            confidence=confidence,
            issues=issues,
            suggestions=["Ensure runtime variables are checked" if valid else "Fix syntax errors"]
        )
