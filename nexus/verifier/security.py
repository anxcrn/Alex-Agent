"""Security scanner for Project Nexus.

Scans Python code blocks using AST parsing to detect dangerous code patterns,
unauthorized filesystem operations, or shell injections.
"""

import ast
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SecurityIssue:
    """A single security vulnerability found in the code."""
    pattern: str
    line: int
    description: str
    severity: str  # 'low', 'medium', 'high', 'critical'


@dataclass
class SecurityResult:
    """Summary of the security scan."""
    safe: bool
    issues: List[SecurityIssue]
    risk_level: str  # 'low', 'medium', 'high', 'critical'


class SecurityScanner(ast.NodeVisitor):
    """AST-based visitor that analyses Python source code for security violations."""

    def __init__(self) -> None:
        self.issues: List[SecurityIssue] = []
        self._current_line = 0

    def scan(self, code: str) -> SecurityResult:
        """Scan a Python code string for issues."""
        self.issues = []
        try:
            tree = ast.parse(code)
            self.visit(tree)
        except SyntaxError as e:
            self.issues.append(SecurityIssue(
                pattern="syntax_error",
                line=e.lineno or 0,
                description=f"Code fails to compile: {e}",
                severity="critical"
            ))
            
        # Additional regex scanning for hardcoded secrets
        self._scan_regex_secrets(code)
        
        # Determine safety and overall risk
        risk_level = "low"
        safe = True
        for issue in self.issues:
            if issue.severity in ("high", "critical"):
                safe = False
                risk_level = "critical"
            elif issue.severity == "medium" and risk_level != "critical":
                risk_level = "medium"
                
        return SecurityResult(safe=safe, issues=self.issues, risk_level=risk_level)

    def scan_file(self, filepath: str) -> SecurityResult:
        """Scan a file path directly."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                code = f.read()
            return self.scan(code)
        except Exception as e:
            return SecurityResult(
                safe=False,
                issues=[SecurityIssue("file_error", 0, str(e), "critical")],
                risk_level="critical"
            )

    def scan_text(self, text: str) -> SecurityResult:
        """Scan raw text (non-Python) for secrets without running AST compilation."""
        self.issues = []
        self._scan_regex_secrets(text)
        
        risk_level = "low"
        safe = True
        for issue in self.issues:
            if issue.severity in ("high", "critical"):
                safe = False
                risk_level = "critical"
            elif issue.severity == "medium" and risk_level != "critical":
                risk_level = "medium"
                
        return SecurityResult(safe=safe, issues=self.issues, risk_level=risk_level)

    # -- AST checks ---------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        """Inspect all function calls."""
        # 1. Check for eval and exec
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in ("eval", "exec", "__import__", "compile"):
                self.issues.append(SecurityIssue(
                    pattern=name,
                    line=node.lineno,
                    description=f"Forbidden built-in function '{name}' is executed",
                    severity="critical"
                ))

        # 2. Check for os.system or subprocess calls
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if isinstance(node.func.value, ast.Name):
                module = node.func.value.id
                if module == "os" and attr == "system":
                    self.issues.append(SecurityIssue(
                        pattern="os.system",
                        line=node.lineno,
                        description="os.system calls are blocked. Use subprocess.run without shell=True.",
                        severity="high"
                    ))
                elif module == "subprocess" and attr in ("run", "Popen", "call"):
                    # Check for shell=True
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            self.issues.append(SecurityIssue(
                                pattern="subprocess(shell=True)",
                                line=node.lineno,
                                description="subprocess execution with shell=True is blocked.",
                                severity="high"
                            ))
                            
        self.generic_visit(node)

    # -- Regex checks -------------------------------------------------------

    def _scan_regex_secrets(self, code: str) -> None:
        """Scan text using regex patterns to find hardcoded tokens/API keys."""
        secret_patterns = {
            "openai_api_key": r"sk-[a-zA-Z0-9]{32,}",
            "github_token": r"ghp_[a-zA-Z0-9]{36}",
            "generic_token": r"api_key\s*=\s*['\"][a-zA-Z0-9-_]{16,}['\"]"
        }
        
        for name, pattern in secret_patterns.items():
            matches = re.finditer(pattern, code)
            for m in matches:
                # Find line number
                line_no = code[:m.start()].count("\n") + 1
                self.issues.append(SecurityIssue(
                    pattern=name,
                    line=line_no,
                    description=f"Potential hardcoded secret or token '{name}' detected",
                    severity="high"
                ))
