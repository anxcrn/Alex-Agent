import os
import json
from pathlib import Path
from typing import Optional
from tools.registry import registry
from alex_constants import get_alex_home

def _get_artifacts_dir() -> Path:
    home = get_alex_home()
    artifacts_dir = Path(home) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir

def create_artifact(name: str, title: str, content: str) -> str:
    """Create a new artifact markdown file."""
    try:
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        if not safe_name:
            return json.dumps({"success": False, "error": "Invalid artifact name"})
        
        art_dir = _get_artifacts_dir()
        file_path = art_dir / f"{safe_name}.md"
        
        full_content = f"# {title}\n\n{content}"
        file_path.write_text(full_content, encoding="utf-8")
        
        return json.dumps({
            "success": True,
            "name": safe_name,
            "title": title,
            "path": str(file_path.absolute())
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def update_artifact(name: str, content: str) -> str:
    """Update an existing artifact file."""
    try:
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        art_dir = _get_artifacts_dir()
        file_path = art_dir / f"{safe_name}.md"
        if not file_path.exists():
            return json.dumps({"success": False, "error": f"Artifact '{name}' does not exist"})
        
        file_path.write_text(content, encoding="utf-8")
        return json.dumps({
            "success": True,
            "name": safe_name,
            "path": str(file_path.absolute())
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def view_artifact(name: str) -> str:
    """Read artifact content."""
    try:
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        art_dir = _get_artifacts_dir()
        file_path = art_dir / f"{safe_name}.md"
        if not file_path.exists():
            return json.dumps({"success": False, "error": f"Artifact '{name}' does not exist"})
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

registry.register(
    name="create_artifact",
    toolset="artifacts",
    schema={
        "name": "create_artifact",
        "description": "Create a new visual artifact (e.g. implementation plan, report, table, or design spec) that will be displayed side-by-side with the chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Descriptive unique filename identifier, e.g. 'design_spec'"},
                "title": {"type": "string", "description": "The title of the artifact"},
                "content": {"type": "string", "description": "The complete markdown content of the artifact"}
            },
            "required": ["name", "title", "content"],
        },
    },
    handler=lambda args, **kw: create_artifact(
        name=args.get("name", ""),
        title=args.get("title", ""),
        content=args.get("content", "")
    ),
    emoji="🎨"
)

registry.register(
    name="update_artifact",
    toolset="artifacts",
    schema={
        "name": "update_artifact",
        "description": "Update the content of an existing artifact by replacing its entire content.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The filename identifier of the artifact to update"},
                "content": {"type": "string", "description": "The complete updated markdown content"}
            },
            "required": ["name", "content"],
        },
    },
    handler=lambda args, **kw: update_artifact(
        name=args.get("name", ""),
        content=args.get("content", "")
    ),
    emoji="✏️"
)

registry.register(
    name="view_artifact",
    toolset="artifacts",
    schema={
        "name": "view_artifact",
        "description": "Read the contents of an existing artifact.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The filename identifier of the artifact to read"}
            },
            "required": ["name"],
        },
    },
    handler=lambda args, **kw: view_artifact(name=args.get("name", "")),
    emoji="📖"
)
