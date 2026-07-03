#!/usr/bin/env python3
"""Git Tool — structured git operations for the agent.

Provides a unified interface for git operations: clone, init, branch, commit,
push, pull, merge, rebase, log, diff, status, stash, tag, worktree, and
GitHub/GitLab PR management.

Uses subprocess directly (not the terminal tool) so the agent gets structured
JSON results with rich error context instead of raw terminal dumps.
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GIT_TOOL_DEFAULT_WORK_DIR = os.getcwd()

_GIT_OPS = {
    "init": "Initialize a new git repository",
    "clone": "Clone a remote repository",
    "status": "Show working tree status",
    "add": "Stage file(s) for commit",
    "commit": "Create a commit with staged changes",
    "push": "Push commits to remote",
    "pull": "Pull changes from remote (fetch + merge)",
    "fetch": "Fetch changes from remote without merging",
    "branch": "List, create, delete, or rename branches",
    "checkout": "Switch branch or restore files",
    "merge": "Merge a branch into the current branch",
    "rebase": "Rebase current branch onto another commit",
    "log": "Show commit log",
    "diff": "Show changes between commits, branches, or working tree",
    "stash": "Stash or pop working directory changes",
    "tag": "List, create, or delete tags",
    "remote": "Manage remote repositories",
    "worktree": "Manage working trees",
    "reset": "Reset current HEAD to a specified state",
    "config": "Get or set git configuration",
    "clean": "Remove untracked files from working tree",
    "blame": "Show what revision and author last modified each line",
    "bisect": "Binary search to find the commit that introduced a bug",
    "pr_create": "Create a pull request (GitHub/GitLab)",
    "pr_list": "List pull requests (GitHub/GitLab)",
    "pr_checkout": "Checkout a pull request locally",
    "pr_merge": "Merge a pull request (GitHub/GitLab)",
}

GIT_SCHEMA = {
    "name": "git",
    "description": (
        "Execute git operations with structured parameters. "
        "Supports full version control: init, clone, status, add, commit, "
        "push, pull, fetch, branch, checkout, merge, rebase, log, diff, "
        "stash, tag, remote, reset, clean, blame, bisect, worktree, config. "
        "Also supports GitHub/GitLab pull request operations (pr_create, "
        "pr_list, pr_checkout, pr_merge). "
        "Prefer this tool over raw terminal git commands when you need "
        "structured results with error context."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": list(_GIT_OPS.keys()),
                "description": "The git operation to perform.\n\n" + "\n".join(
                    f"  - {k}: {v}" for k, v in _GIT_OPS.items()
                ),
            },
            "repo_path": {
                "type": "string",
                "description": (
                    "Path to the git repository working directory. "
                    "Defaults to current working directory."
                ),
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Additional arguments for the git operation. "
                    "Examples:\n"
                    "  - init: []\n"
                    "  - clone: ['https://github.com/user/repo.git', './local-dir']\n"
                    "  - add: ['.'] or ['src/main.py', 'src/utils.py']\n"
                    "  - commit: ['-m', 'Add feature']\n"
                    "  - branch: ['feature-x'] (create) or ['-d', 'old-branch'] (delete)\n"
                    "  - checkout: ['-b', 'new-branch'] or ['main']\n"
                    "  - log: ['--oneline', '-10']\n"
                    "  - diff: ['--cached'] or ['HEAD~1', 'HEAD']\n"
                    "  - push: ['origin', 'main']\n"
                    "  - pull: ['origin', 'main']\n"
                    "  - merge: ['feature-branch']\n"
                    "  - rebase: ['main']\n"
                    "  - stash: ['push', '-m', 'WIP'] or ['pop'] or ['list']\n"
                    "  - tag: ['v1.0.0'] or ['-d', 'v1.0.0']\n"
                    "  - reset: ['--hard', 'HEAD~1']\n"
                    "  - remote: ['-v'] or ['add', 'origin', '<url>']"
                ),
            },
            "message": {
                "type": "string",
                "description": "Commit message (required for commit operation).",
            },
            "remote_url": {
                "type": "string",
                "description": "Remote URL (required for clone operation).",
            },
            "branch_name": {
                "type": "string",
                "description": "Branch name for branch/checkout operations.",
            },
            "pr_title": {
                "type": "string",
                "description": "Pull request title (required for pr_create).",
            },
            "pr_body": {
                "type": "string",
                "description": "Pull request body/description.",
            },
            "pr_head": {
                "type": "string",
                "description": "Source branch for PR (defaults to current branch).",
            },
            "pr_base": {
                "type": "string",
                "description": "Target branch for PR (defaults to 'main').",
            },
        },
        "required": ["operation"],
    },
}


def _run_git(args: List[str], cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run a git command and return structured results."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd or GIT_TOOL_DEFAULT_WORK_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": "git " + " ".join(args),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "git command timed out after 120 seconds",
            "command": "git " + " ".join(args),
        }
    except FileNotFoundError:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "git not found. Install git and ensure it is in PATH.",
            "command": "git " + " ".join(args),
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Error running git: {e}",
            "command": "git " + " ".join(args),
        }


def _get_remote_url(cwd: str) -> Optional[str]:
    """Get the remote origin URL for the repo at cwd."""
    result = _run_git(["config", "--get", "remote.origin.url"], cwd)
    if result["success"]:
        return result["stdout"].strip()
    return None


def _detect_git_platform(remote_url: str) -> Optional[str]:
    """Detect GitHub or GitLab from remote URL."""
    if not remote_url:
        return None
    if "github.com" in remote_url:
        return "github"
    if "gitlab.com" in remote_url or "gitlab" in remote_url:
        return "gitlab"
    return None


def _parse_owner_repo(remote_url: str) -> Optional[Dict[str, str]]:
    """Parse owner/repo from a remote URL."""
    patterns = [
        r"github\.com[/:]([^/]+)/([^/.]+)",
        r"gitlab\.com[/:]([^/]+)/([^/.]+)",
    ]
    for p in patterns:
        m = re.search(p, remote_url)
        if m:
            return {"owner": m.group(1), "repo": m.group(2).removesuffix(".git")}
    return None


def _handle_pr_create(operation: str, args: List[str], cwd: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a pull request via GitHub CLI (gh) or GitLab CLI (glab)."""
    remote_url = _get_remote_url(cwd)
    if not remote_url:
        return {"success": False, "error": "No remote origin URL configured", "command": "pr_create"}

    platform = _detect_git_platform(remote_url)
    if platform == "github":
        gh_args = ["pr", "create"]
        title = params.get("pr_title")
        if title:
            gh_args.extend(["--title", title])
        body = params.get("pr_body")
        if body:
            gh_args.extend(["--body", body])
        head = params.get("pr_head")
        if head:
            gh_args.extend(["--head", head])
        base = params.get("pr_base") or "main"
        gh_args.extend(["--base", base])

        try:
            result = subprocess.run(
                ["gh"] + gh_args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "success": result.returncode == 0,
                "url": result.stdout.strip() if result.returncode == 0 else None,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": "gh " + " ".join(gh_args),
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "GitHub CLI (gh) not found. Install it from https://cli.github.com/",
                "command": "pr_create",
            }

    elif platform == "gitlab":
        try:
            glab_args = ["mr", "create"]
            title = params.get("pr_title")
            if title:
                glab_args.extend(["--title", title])
            body = params.get("pr_body")
            if body:
                glab_args.extend(["--description", body])
            head = params.get("pr_head")
            if head:
                glab_args.extend(["--source-branch", head])
            base = params.get("pr_base") or "main"
            glab_args.extend(["--target-branch", base])

            result = subprocess.run(
                ["glab"] + glab_args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "success": result.returncode == 0,
                "url": result.stdout.strip() if result.returncode == 0 else None,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": "glab " + " ".join(glab_args),
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "GitLab CLI (glab) not found. Install it from https://gitlab.com/gitlab-org/cli",
                "command": "pr_create",
            }
    else:
        return {"success": False, "error": f"Unsupported platform for remote: {remote_url}", "command": "pr_create"}


def _handle_pr_list(operation: str, args: List[str], cwd: str, params: Dict[str, Any]) -> Dict[str, Any]:
    remote_url = _get_remote_url(cwd)
    if not remote_url:
        return {"success": False, "error": "No remote origin URL configured", "command": "pr_list"}
    platform = _detect_git_platform(remote_url)

    if platform == "github":
        try:
            result = subprocess.run(
                ["gh", "pr", "list"] + args,
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except FileNotFoundError:
            return {"success": False, "error": "GitHub CLI (gh) not found"}
    elif platform == "gitlab":
        try:
            result = subprocess.run(
                ["glab", "mr", "list"] + args,
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except FileNotFoundError:
            return {"success": False, "error": "GitLab CLI (glab) not found"}
    else:
        return {"success": False, "error": f"Unsupported platform: {remote_url}"}


def _handle_pr_checkout(operation: str, args: List[str], cwd: str, params: Dict[str, Any]) -> Dict[str, Any]:
    remote_url = _get_remote_url(cwd)
    if not remote_url:
        return {"success": False, "error": "No remote origin URL configured", "command": "pr_checkout"}
    platform = _detect_git_platform(remote_url)

    if platform == "github":
        try:
            result = subprocess.run(
                ["gh", "pr", "checkout"] + args,
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except FileNotFoundError:
            return {"success": False, "error": "GitHub CLI (gh) not found"}
    elif platform == "gitlab":
        try:
            result = subprocess.run(
                ["glab", "mr", "checkout"] + args,
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except FileNotFoundError:
            return {"success": False, "error": "GitLab CLI (glab) not found"}
    else:
        return {"success": False, "error": f"Unsupported platform: {remote_url}"}


def _handle_pr_merge(operation: str, args: List[str], cwd: str, params: Dict[str, Any]) -> Dict[str, Any]:
    remote_url = _get_remote_url(cwd)
    if not remote_url:
        return {"success": False, "error": "No remote origin URL configured", "command": "pr_merge"}
    platform = _detect_git_platform(remote_url)

    if platform == "github":
        try:
            result = subprocess.run(
                ["gh", "pr", "merge"] + args,
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except FileNotFoundError:
            return {"success": False, "error": "GitHub CLI (gh) not found"}
    elif platform == "gitlab":
        try:
            result = subprocess.run(
                ["glab", "mr", "merge"] + args,
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except FileNotFoundError:
            return {"success": False, "error": "GitLab CLI (glab) not found"}
    else:
        return {"success": False, "error": f"Unsupported platform: {remote_url}"}


def check_git_requirements() -> bool:
    return True


def git_tool(
    operation: str = "",
    repo_path: Optional[str] = None,
    args: Optional[List[str]] = None,
    message: Optional[str] = None,
    remote_url: Optional[str] = None,
    branch_name: Optional[str] = None,
    pr_title: Optional[str] = None,
    pr_body: Optional[str] = None,
    pr_head: Optional[str] = None,
    pr_base: Optional[str] = None,
) -> str:
    cwd = repo_path or GIT_TOOL_DEFAULT_WORK_DIR
    args = args or []
    params = {
        "pr_title": pr_title,
        "pr_body": pr_body,
        "pr_head": pr_head,
        "pr_base": pr_base,
    }

    if operation == "pr_create":
        result = _handle_pr_create(operation, args, cwd, params)
        return json.dumps(result)

    if operation == "pr_list":
        result = _handle_pr_list(operation, args, cwd, params)
        return json.dumps(result)

    if operation == "pr_checkout":
        result = _handle_pr_checkout(operation, args, cwd, params)
        return json.dumps(result)

    if operation == "pr_merge":
        result = _handle_pr_merge(operation, args, cwd, params)
        return json.dumps(result)

    if operation == "clone":
        url = remote_url or (args[0] if args else None)
        if not url:
            return json.dumps({"success": False, "error": "remote_url is required for clone"})
        git_args = ["clone", url] + args[1:]
        result = _run_git(git_args)
        if result["success"]:
            repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
            result["repo_path"] = str(Path(cwd) / repo_name)
        return json.dumps(result)

    if operation == "commit":
        if message:
            git_args = ["commit", "-m", message] + args
        else:
            git_args = ["commit"] + args
        result = _run_git(git_args, cwd)
        return json.dumps(result)

    if operation == "init":
        git_args = ["init"] + args
        result = _run_git(git_args, cwd)
        return json.dumps(result)

    if operation in ("branch", "checkout"):
        if branch_name:
            git_args = [operation, branch_name] + args
        else:
            git_args = [operation] + args
        result = _run_git(git_args, cwd)
        return json.dumps(result)

    if operation == "config":
        git_args = ["config"] + args
        result = _run_git(git_args, cwd)
        return json.dumps(result)

    git_args = [operation] + args
    result = _run_git(git_args, cwd)
    return json.dumps(result)


from tools.registry import registry

registry.register(
    name="git",
    toolset="dev",
    schema=GIT_SCHEMA,
    handler=lambda args, **kw: git_tool(
        operation=args.get("operation", ""),
        repo_path=args.get("repo_path"),
        args=args.get("args"),
        message=args.get("message"),
        remote_url=args.get("remote_url"),
        branch_name=args.get("branch_name"),
        pr_title=args.get("pr_title"),
        pr_body=args.get("pr_body"),
        pr_head=args.get("pr_head"),
        pr_base=args.get("pr_base"),
    ),
    check_fn=check_git_requirements,
    emoji="🔀",
)
