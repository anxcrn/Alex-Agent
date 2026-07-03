#!/usr/bin/env python3
"""Dev Tool — structured development operations.

Provides a unified interface for common dev workflows that the agent
would otherwise handle through ad-hoc terminal commands. Auto-detects
project type and toolchain so the agent doesn't have to remember the
exact command for every language's test framework, linter, or builder.

Operations:
  - test:    Run project tests (auto-detects framework)
  - lint:    Run linter (auto-detects configured linter)
  - format:  Format source code (auto-detects formatter)
  - build:   Build the project (auto-detects build system)
  - clean:   Clean build artifacts
  - install: Install dependencies
  - audit:   Run security audit on dependencies
  - typecheck: Run type checker (mypy, pyright, tsc, etc.)
  - outdated: List outdated dependencies
  - coverage: Run tests with coverage reporting
  - ci:      Run the CI pipeline locally (test + lint + typecheck)
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


DEV_OPS = {
    "test": "Run project tests with auto-detected test framework",
    "lint": "Run linter (ruff, pylint, eslint, clippy, etc.)",
    "format": "Format source code (ruff format, prettier, black, gofmt, rustfmt)",
    "build": "Build the project (npm build, cargo build, go build, make, etc.)",
    "clean": "Clean build artifacts (node_modules, target, dist, __pycache__)",
    "install": "Install project dependencies",
    "audit": "Run security audit on dependencies",
    "typecheck": "Run type checker (mypy, pyright, tsc, flow, etc.)",
    "outdated": "List outdated dependencies",
    "coverage": "Run tests with coverage reporting",
    "ci": "Run full CI pipeline locally (test + lint + typecheck + build)",
    "fix": "Auto-fix lint issues (ruff --fix, eslint --fix, etc.)",
}

DEV_SCHEMA = {
    "name": "dev",
    "description": (
        "Structured development operations: test, lint, format, build, "
        "install, clean, audit, typecheck, coverage, outdated, fix, ci. "
        "Auto-detects project type (Python, JavaScript/TypeScript, Rust, Go, "
        "Java/Kotlin, C/C++, etc.) and the correct toolchain commands. "
        "Prefer this over raw terminal commands for standard dev workflows "
        "to get structured output with parsed results."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": list(DEV_OPS.keys()),
                "description": "The development operation.\n\n" + "\n".join(
                    f"  - {k}: {v}" for k, v in DEV_OPS.items()
                ),
            },
            "project_path": {
                "type": "string",
                "description": "Path to the project root. Defaults to current directory.",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Additional arguments passed through to the underlying tool. "
                    "Examples: test -- ['-v', '-k', 'test_name'], "
                    "lint -- ['--select', 'F401'], "
                    "build -- ['--release']"
                ),
            },
            "target": {
                "type": "string",
                "description": (
                    "Specific target for the operation. "
                    "For test: specific test file or pattern. "
                    "For lint/build: specific package/module. "
                    "For install: specific package name."
                ),
            },
        },
        "required": ["operation"],
    },
}


def _detect_project_type(project_path: str) -> Dict[str, Any]:
    """Auto-detect the project type and available toolchain."""
    root = Path(project_path)
    info: Dict[str, Any] = {
        "project_type": "unknown",
        "package_manager": None,
        "test_framework": None,
        "linter": None,
        "formatter": None,
        "build_system": None,
        "type_checker": None,
    }

    has_pyproject = (root / "pyproject.toml").exists()
    has_setup_py = (root / "setup.py").exists()
    has_setup_cfg = (root / "setup.cfg").exists()
    has_requirements = (root / "requirements.txt").exists()
    has_package_json = (root / "package.json").exists()
    has_cargo_toml = (root / "Cargo.toml").exists()
    has_go_mod = (root / "go.mod").exists()
    has_gradle = (root / "build.gradle").exists() or (root / "build.gradle.kts").exists()
    has_maven = (root / "pom.xml").exists()
    has_makefile = (root / "Makefile").exists()
    has_justfile = (root / "justfile").exists()
    has_cmake = (root / "CMakeLists.txt").exists()

    if has_pyproject or has_setup_py or has_setup_cfg or has_requirements:
        info["project_type"] = "python"
        if has_pyproject:
            info["build_system"] = "hatchling" if _file_contains(root / "pyproject.toml", "hatchling") else "setuptools"
            info["linter"] = "ruff" if _file_contains(root / "pyproject.toml", "[tool.ruff]") or _file_contains(root / "pyproject.toml", "ruff") else "pylint"
            info["formatter"] = "ruff" if _file_contains(root / "pyproject.toml", "[tool.ruff.format]") else "black"
            info["type_checker"] = "mypy" if _file_contains(root / "pyproject.toml", "[tool.mypy]") else "pyright"
        info["test_framework"] = "pytest" if (root / "pytest.ini").exists() or _file_contains_str(root / "pyproject.toml", "pytest") or (root / "conftest.py").exists() else "unittest"

    elif has_package_json:
        info["project_type"] = "javascript"
        pkg = _read_json(root / "package.json") if (root / "package.json").exists() else {}
        if pkg:
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "yarn" in str(root / ".yarnrc.yml") or (root / "yarn.lock").exists():
                info["package_manager"] = "yarn"
            elif (root / "pnpm-lock.yaml").exists():
                info["package_manager"] = "pnpm"
            else:
                info["package_manager"] = "npm"
            if "jest" in deps:
                info["test_framework"] = "jest"
            elif "vitest" in deps:
                info["test_framework"] = "vitest"
            elif "mocha" in deps:
                info["test_framework"] = "mocha"
            elif "ava" in deps:
                info["test_framework"] = "ava"
            if "eslint" in deps:
                info["linter"] = "eslint"
            elif "biome" in deps:
                info["linter"] = "biome"
            if "prettier" in deps:
                info["formatter"] = "prettier"
            if "typescript" in deps:
                info["project_type"] = "typescript"
                info["type_checker"] = "tsc"
                info["build_system"] = "tsc"

    elif has_cargo_toml:
        info["project_type"] = "rust"
        info["package_manager"] = "cargo"
        info["build_system"] = "cargo"
        info["test_framework"] = "cargo test"
        info["linter"] = "clippy"
        info["formatter"] = "rustfmt"
        info["type_checker"] = "cargo check"

    elif has_go_mod:
        info["project_type"] = "go"
        info["package_manager"] = "go mod"
        info["build_system"] = "go build"
        info["test_framework"] = "go test"
        info["formatter"] = "gofmt"
        info["linter"] = "golangci-lint"

    elif has_gradle:
        info["project_type"] = "kotlin" if _file_contains_str(root / "build.gradle.kts", "kotlin") else "java"
        info["build_system"] = "gradle"
        info["test_framework"] = "gradle test"
        info["linter"] = "ktlint" if info["project_type"] == "kotlin" else "checkstyle"

    elif has_maven:
        info["project_type"] = "java"
        info["build_system"] = "maven"
        info["test_framework"] = "maven test"
        info["linter"] = "checkstyle"

    if has_makefile:
        info["build_system"] = "make"

    if has_justfile:
        info["build_system"] = "just"

    if has_cmake:
        info["build_system"] = "cmake"

    return info


def _file_contains(path: Path, pattern: str) -> bool:
    """Check if a file contains a substring (simple text search)."""
    try:
        return path.exists() and pattern in path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False


def _file_contains_str(path: Path, text: str) -> bool:
    """Check if a file contains a specific string."""
    try:
        if path.exists():
            return text in path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        pass
    return False


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run_cmd(cmd: List[str], cwd: str, timeout: int = 300) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "returncode": -1, "stdout": "", "stderr": f"Command timed out after {timeout}s", "command": " ".join(cmd)}
    except FileNotFoundError:
        return {"success": False, "returncode": -1, "stdout": "", "stderr": f"Command not found: {cmd[0]}. Is it installed?", "command": " ".join(cmd)}
    except Exception as e:
        return {"success": False, "returncode": -1, "stdout": "", "stderr": f"Error: {e}", "command": " ".join(cmd)}


def _has_tool(name: str) -> bool:
    try:
        subprocess.run([name, "--version"], capture_output=True, text=True, timeout=10)
        return True
    except Exception:
        return False


def _handle_test(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]
    target_args = [target] if target else []

    if pt == "python":
        if info["test_framework"] == "pytest" or _has_tool("pytest"):
            return _run_cmd(["pytest"] + target_args + args, project_path)
        return _run_cmd([sys.executable, "-m", "unittest"] + target_args + args, project_path)

    if pt in ("javascript", "typescript"):
        pm = info["package_manager"] or "npm"
        if pm == "yarn":
            return _run_cmd(["yarn", "test"] + target_args + args, project_path)
        elif pm == "pnpm":
            return _run_cmd(["pnpm", "test"] + target_args + args, project_path)
        return _run_cmd(["npm", "test", "--"] + target_args + args, project_path)

    if pt == "rust":
        return _run_cmd(["cargo", "test"] + args, project_path)

    if pt == "go":
        target_path = target if target else "./..."
        return _run_cmd(["go", "test"] + target_args + args + [target_path], project_path)

    if info["build_system"] == "gradle":
        return _run_cmd(["gradle", "test"] + args, project_path)

    if info["build_system"] == "maven":
        return _run_cmd(["mvn", "test"] + args, project_path)

    if info["build_system"] == "make":
        return _run_cmd(["make", "test"] + args, project_path)

    if info["build_system"] == "just":
        return _run_cmd(["just", "test"] + args, project_path)

    return {"success": False, "error": f"Could not determine test command for project type: {pt}"}


def _handle_lint(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]

    if pt == "python":
        linter = info["linter"] or "ruff"
        if linter == "ruff" and _has_tool("ruff"):
            target_path = target or "."
            return _run_cmd(["ruff", "check"] + args + [target_path], project_path)
        elif _has_tool("pylint"):
            target_path = target or "."
            return _run_cmd(["pylint"] + args + [target_path], project_path)
        return _run_cmd([sys.executable, "-m", "ruff", "check"] + args + [target or "."], project_path)

    if pt in ("javascript", "typescript"):
        pm = info["package_manager"] or "npm"
        if info["linter"] == "biome":
            return _run_cmd(["npx", "biome", "check"] + args + [target or "."], project_path)
        if info["linter"] == "eslint":
            return _run_cmd(["npx", "eslint"] + args + [target or "."], project_path)
        return _run_cmd([pm, "run", "lint"] + args, project_path)

    if pt == "rust":
        return _run_cmd(["cargo", "clippy"] + args, project_path)

    if pt == "go":
        if _has_tool("golangci-lint"):
            return _run_cmd(["golangci-lint", "run"] + args, project_path)
        return _run_cmd(["go", "vet"] + args + [target or "./..."], project_path)

    return {"success": False, "error": f"Could not determine linter for project type: {pt}"}


def _handle_format(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]
    check_mode = "--check" in args or "check" in args

    if pt == "python":
        formatter = info["formatter"] or "ruff"
        fmt_args = ["format", "--check"] if check_mode else ["format"]
        if formatter == "ruff" or _has_tool("ruff"):
            return _run_cmd(["ruff"] + fmt_args + args + [target or "."], project_path)
        if _has_tool("black"):
            check_flag = ["--check"] if check_mode else []
            return _run_cmd(["black"] + check_flag + args + [target or "."], project_path)
        return _run_cmd([sys.executable, "-m", "ruff", "format"] + args + [target or "."], project_path)

    if pt in ("javascript", "typescript"):
        if _has_tool("prettier") or (Path(project_path) / "node_modules" / ".bin" / "prettier").exists():
            check_flag = ["--check"] if check_mode else []
            return _run_cmd(["npx", "prettier"] + check_flag + args + [target or "."], project_path)
        pm = info["package_manager"] or "npm"
        fmt_cmd = "format:check" if check_mode else "format"
        return _run_cmd([pm, "run", fmt_cmd] + args, project_path)

    if pt == "rust":
        check_flag = ["--check"] if check_mode else []
        return _run_cmd(["cargo", "fmt"] + check_flag + args, project_path)

    if pt == "go":
        if check_mode:
            return _run_cmd(["gofmt", "-l", target or "."], project_path)
        return _run_cmd(["gofmt", "-w", target or "."], project_path)

    return {"success": False, "error": f"Could not determine formatter for project type: {pt}"}


def _handle_build(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]

    if pt == "python":
        if (Path(project_path) / "pyproject.toml").exists():
            return _run_cmd([sys.executable, "-m", "build"] + args, project_path)
        return {"success": False, "error": "Python project without pyproject.toml (no standard build). Use setup.py install or pip install -e ."}

    if pt in ("javascript", "typescript"):
        pm = info["package_manager"] or "npm"
        if pm == "yarn":
            return _run_cmd(["yarn", "build"] + args, project_path)
        elif pm == "pnpm":
            return _run_cmd(["pnpm", "build"] + args, project_path)
        return _run_cmd(["npm", "run", "build"] + args, project_path)

    if pt == "rust":
        return _run_cmd(["cargo", "build"] + args, project_path)

    if pt == "go":
        return _run_cmd(["go", "build"] + args, project_path)

    if info["build_system"] == "gradle":
        return _run_cmd(["gradle", "build"] + args, project_path)

    if info["build_system"] == "maven":
        return _run_cmd(["mvn", "compile"] + args, project_path)

    if info["build_system"] == "make":
        return _run_cmd(["make", target or "all"] + args, project_path)

    if info["build_system"] == "cmake":
        return _run_cmd(["cmake", "--build", "."] + args, project_path)

    return {"success": False, "error": f"Could not determine build command for project type: {pt}"}


def _handle_clean(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    results = []
    root = Path(project_path)
    dirs_to_clean = []

    pt = info["project_type"]
    if pt == "python":
        for p in root.rglob("__pycache__"):
            dirs_to_clean.append(str(p))
        for p in root.rglob("*.pyc"):
            try:
                p.unlink()
            except Exception:
                pass
        for d in ["build", "dist", "*.egg-info", ".pytest_cache", ".mypy_cache", ".ruff_cache"]:
            for p in root.glob(d):
                if p.is_dir():
                    dirs_to_clean.append(str(p))
    elif pt in ("javascript", "typescript"):
        for d in ["node_modules", "dist", "build", ".next", "out", "coverage"]:
            p = root / d
            if p.exists():
                dirs_to_clean.append(str(p))
    elif pt == "rust":
        p = root / "target"
        if p.exists():
            dirs_to_clean.append(str(p))
    elif pt == "go":
        pass

    for d in dirs_to_clean:
        try:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
            results.append(f"Removed: {d}")
        except Exception as e:
            results.append(f"Failed to remove {d}: {e}")

    return {"success": True, "cleaned_dirs": results, "count": len(results)}


def _handle_install(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]

    if pt == "python":
        if (Path(project_path) / "uv.lock").exists() and _has_tool("uv"):
            return _run_cmd(["uv", "sync"] + args, project_path)
        if (Path(project_path) / "requirements.txt").exists():
            return _run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"] + args, project_path)
        return _run_cmd([sys.executable, "-m", "pip", "install", "-e", "."] + args, project_path)

    if pt in ("javascript", "typescript"):
        pm = info["package_manager"] or "npm"
        if pm == "yarn":
            return _run_cmd(["yarn", "install"] + args, project_path)
        elif pm == "pnpm":
            return _run_cmd(["pnpm", "install"] + args, project_path)
        return _run_cmd(["npm", "install"] + args, project_path)

    if pt == "rust":
        return _run_cmd(["cargo", "build"] + args, project_path)

    if pt == "go":
        return _run_cmd(["go", "mod", "download"] + args, project_path)

    if info["build_system"] == "gradle":
        return _run_cmd(["gradle", "build"] + args, project_path)

    return {"success": False, "error": f"Could not determine install command for project type: {pt}"}


def _handle_audit(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]

    if pt == "python":
        if _has_tool("pip-audit"):
            return _run_cmd(["pip-audit"] + args, project_path)
        return {"success": False, "error": "pip-audit not available. Install with: pip install pip-audit", "project_type": "python"}

    if pt in ("javascript", "typescript"):
        pm = info["package_manager"] or "npm"
        if pm == "yarn":
            return _run_cmd(["yarn", "audit"] + args, project_path)
        elif pm == "pnpm":
            return _run_cmd(["pnpm", "audit"] + args, project_path)
        return _run_cmd(["npm", "audit"] + args, project_path)

    if pt == "rust":
        if _has_tool("cargo-audit"):
            return _run_cmd(["cargo", "audit"] + args, project_path)
        return {"success": False, "error": "cargo-audit not installed. Install with: cargo install cargo-audit"}

    if pt == "go":
        return _run_cmd(["go", "vulncheck"] + args + ["./..."], project_path)

    return {"success": False, "error": f"Could not determine audit command for project type: {pt}"}


def _handle_typecheck(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]

    if pt == "python":
        tc = info["type_checker"] or "mypy"
        if tc == "mypy" and _has_tool("mypy"):
            return _run_cmd(["mypy"] + args + [target or "."], project_path)
        elif _has_tool("pyright"):
            return _run_cmd(["pyright"] + args + [target or "."], project_path)
        elif _has_tool("pylance"):
            return _run_cmd(["pyright"] + args + [target or "."], project_path)
        return _run_cmd([sys.executable, "-m", "mypy"] + args + [target or "."], project_path)

    if pt == "typescript":
        return _run_cmd(["npx", "tsc", "--noEmit"] + args, project_path)

    if pt == "rust":
        return _run_cmd(["cargo", "check"] + args, project_path)

    if pt == "go":
        return _run_cmd(["go", "vet"] + args + [target or "./..."], project_path)

    return {"success": False, "error": f"Could not determine type checker for project type: {pt}"}


def _handle_outdated(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]

    if pt == "python":
        if _has_tool("pip"):
            return _run_cmd([sys.executable, "-m", "pip", "list", "--outdated"] + args, project_path)
        if _has_tool("uv"):
            return _run_cmd(["uv", "pip", "list", "--outdated"] + args, project_path)

    if pt in ("javascript", "typescript"):
        pm = info["package_manager"] or "npm"
        if pm == "yarn":
            return _run_cmd(["yarn", "outdated"] + args, project_path)
        elif pm == "pnpm":
            return _run_cmd(["pnpm", "outdated"] + args, project_path)
        return _run_cmd(["npm", "outdated"] + args, project_path)

    if pt == "rust":
        return _run_cmd(["cargo", "outdated"] + args, project_path)

    if pt == "go":
        return _run_cmd(["go", "list", "-u", "-m", "all"] + args, project_path)

    return {"success": False, "error": f"Could not determine outdated command for project type: {pt}"}


def _handle_coverage(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]

    if pt == "python":
        if _has_tool("pytest") and _has_tool("coverage"):
            return _run_cmd(
                ["coverage", "run", "-m", "pytest"] + ([target] if target else []) + args,
                project_path,
            )
        return _run_cmd(
            [sys.executable, "-m", "coverage", "run", "-m", "pytest"] + ([target] if target else []) + args,
            project_path,
        )

    if pt == "rust":
        return _run_cmd(["cargo", "tarpaulin"] + args, project_path)

    if pt == "go":
        return _run_cmd(["go", "test", "-coverprofile=coverage.out"] + args + [target or "./..."], project_path)

    pm = info.get("package_manager", "npm")
    return _run_cmd([pm, "run", "test:coverage"] + args, project_path)


def _handle_ci(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    steps = []

    lint_result = _handle_lint(info, project_path, target, args)
    steps.append({"step": "lint", "success": lint_result.get("success", False), "output": lint_result})

    if lint_result.get("success", False):
        test_result = _handle_test(info, project_path, target, args)
        steps.append({"step": "test", "success": test_result.get("success", False), "output": test_result})

        typecheck_result = _handle_typecheck(info, project_path, target, args)
        steps.append({"step": "typecheck", "success": typecheck_result.get("success", False), "output": typecheck_result})

        build_result = _handle_build(info, project_path, target, args)
        steps.append({"step": "build", "success": build_result.get("success", False), "output": build_result})

    all_passed = all(s["success"] for s in steps)
    return {"success": all_passed, "project_type": info["project_type"], "steps": steps, "all_passed": all_passed}


def _handle_fix(info: Dict[str, Any], project_path: str, target: Optional[str], args: List[str]) -> Dict[str, Any]:
    pt = info["project_type"]

    if pt == "python":
        if info["linter"] == "ruff" or _has_tool("ruff"):
            return _run_cmd(["ruff", "check", "--fix"] + args + [target or "."], project_path)
        return _run_cmd([sys.executable, "-m", "ruff", "check", "--fix"] + args + [target or "."], project_path)

    if pt in ("javascript", "typescript"):
        if info["linter"] == "eslint":
            return _run_cmd(["npx", "eslint", "--fix"] + args + [target or "."], project_path)
        if info["linter"] == "biome":
            return _run_cmd(["npx", "biome", "check", "--apply"] + args + [target or "."], project_path)
        return _run_cmd(["npx", "eslint", "--fix"] + args + [target or "."], project_path)

    if pt == "rust":
        return _run_cmd(["cargo", "fix"] + args, project_path)

    if pt == "go":
        return _run_cmd(["gofmt", "-s", "-w", target or "."], project_path)

    return {"success": False, "error": f"Could not determine auto-fix for project type: {pt}"}


def check_dev_requirements() -> bool:
    return True


def dev_tool(
    operation: str = "",
    project_path: Optional[str] = None,
    args: Optional[List[str]] = None,
    target: Optional[str] = None,
) -> str:
    pp = project_path or os.getcwd()
    args = args or []

    info = _detect_project_type(pp)

    handlers = {
        "test": _handle_test,
        "lint": _handle_lint,
        "format": _handle_format,
        "build": _handle_build,
        "clean": _handle_clean,
        "install": _handle_install,
        "audit": _handle_audit,
        "typecheck": _handle_typecheck,
        "outdated": _handle_outdated,
        "coverage": _handle_coverage,
        "ci": _handle_ci,
        "fix": _handle_fix,
    }

    handler = handlers.get(operation)
    if not handler:
        return json.dumps({"success": False, "error": f"Unknown operation: {operation}"})

    try:
        result = handler(info, pp, target, args)
    except Exception as e:
        logger.exception("dev tool %s failed: %s", operation, e)
        result = {"success": False, "error": f"{operation} failed: {e}"}

    if isinstance(result, dict) and "project_type" not in result:
        result["project_type"] = info["project_type"]

    return json.dumps(result)


from tools.registry import registry

registry.register(
    name="dev",
    toolset="dev",
    schema=DEV_SCHEMA,
    handler=lambda args, **kw: dev_tool(
        operation=args.get("operation", ""),
        project_path=args.get("project_path"),
        args=args.get("args"),
        target=args.get("target"),
    ),
    check_fn=check_dev_requirements,
    emoji="🛠️",
)
