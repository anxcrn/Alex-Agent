import base64
import mimetypes
import os
import json
from pathlib import Path
from typing import Optional
from tools.registry import registry
from alex_constants import get_alex_home

_ARTIFACT_TYPES = {
    ".md": "markdown",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".txt": "text",
    ".csv": "csv",
    ".svg": "svg",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".ico": "image",
    ".pdf": "pdf",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
}

def _get_artifacts_dir() -> Path:
    home = get_alex_home()
    artifacts_dir = Path(home) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir

def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".")).strip().lower()

def _detect_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    return _ARTIFACT_TYPES.get(ext, "text")

def create_artifact(
    name: str, title: str, content: str,
    type_hint: str = "",
    binary_content: str = "",
) -> str:
    """Create a new artifact.

    Args:
        name: Filename (e.g. ``design_spec.md`` or ``chart.png``).
        title: Display title.
        content: Text content (for markdown, html, json, txt, etc.).
        type_hint: Override auto-detected type (``markdown``, ``html``, ``json``,
            ``text``, ``csv``, ``svg``, ``image``, ``pdf``, ``yaml``, ``toml``, ``xml``).
        binary_content: Base64-encoded binary content (for images, PDFs).
    """
    try:
        safe = _safe_name(name)
        if not safe:
            return json.dumps({"success": False, "error": "Invalid artifact name"})

        art_dir = _get_artifacts_dir()
        file_path = art_dir / safe

        if binary_content:
            file_path.write_bytes(base64.b64decode(binary_content))
        else:
            full_content = f"# {title}\n\n{content}" if title and safe.endswith(".md") else content
            file_path.write_text(full_content, encoding="utf-8")

        art_type = type_hint or _detect_type(file_path)

        return json.dumps({
            "success": True,
            "name": safe,
            "title": title,
            "type": art_type,
            "path": str(file_path.absolute()),
        })
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})

def update_artifact(name: str, content: str) -> str:
    """Update an existing artifact."""
    try:
        safe = _safe_name(name)
        art_dir = _get_artifacts_dir()
        file_path = art_dir / safe
        if not file_path.exists():
            return json.dumps({"success": False, "error": f"Artifact '{name}' does not exist"})

        file_path.write_text(content, encoding="utf-8")
        return json.dumps({
            "success": True,
            "name": safe,
            "path": str(file_path.absolute()),
        })
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})

def view_artifact(name: str) -> str:
    """Read artifact content."""
    try:
        safe = _safe_name(name)
        art_dir = _get_artifacts_dir()
        file_path = art_dir / safe
        if not file_path.exists():
            # Try with .md extension for backward compat
            file_path = art_dir / f"{safe}.md"
        if not file_path.exists():
            return json.dumps({"success": False, "error": f"Artifact '{name}' does not exist"})

        art_type = _detect_type(file_path)
        if art_type == "image":
            b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
            return json.dumps({"success": True, "type": "image", "content": b64, "name": safe})
        return json.dumps({"success": True, "type": "text", "content": file_path.read_text(encoding="utf-8"), "name": safe})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})

def delete_artifact(name: str) -> str:
    """Delete an artifact."""
    try:
        safe = _safe_name(name)
        art_dir = _get_artifacts_dir()
        file_path = art_dir / safe
        if not file_path.exists():
            file_path = art_dir / f"{safe}.md"
        if not file_path.exists():
            return json.dumps({"success": False, "error": f"Artifact '{name}' does not exist"})
        file_path.unlink()
        return json.dumps({"success": True, "name": safe})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})

registry.register(
    name="create_artifact",
    toolset="artifacts",
    schema={
        "name": "create_artifact",
        "description": "Create a new visual artifact (markdown, HTML, image, JSON, CSV, SVG, PDF) that will be displayed side-by-side with the chat or downloaded.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Filename with extension, e.g. 'design_spec.md' or 'chart.png'"},
                "title": {"type": "string", "description": "Display title of the artifact"},
                "content": {"type": "string", "description": "Text content (for markdown, html, json, txt, csv, svg, yaml, xml)"},
                "type_hint": {"type": "string", "description": "Override type: markdown, html, json, text, csv, svg, image, pdf, yaml, toml, xml"},
                "binary_content": {"type": "string", "description": "Base64-encoded binary content (for images, PDFs)"},
            },
            "required": ["name", "title"],
        },
    },
    handler=lambda args, **kw: create_artifact(
        name=args.get("name", ""),
        title=args.get("title", ""),
        content=args.get("content", ""),
        type_hint=args.get("type_hint", ""),
        binary_content=args.get("binary_content", ""),
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
                "name": {"type": "string", "description": "The filename of the artifact to read"}
            },
            "required": ["name"],
        },
    },
    handler=lambda args, **kw: view_artifact(name=args.get("name", "")),
    emoji="📖"
)

registry.register(
    name="delete_artifact",
    toolset="artifacts",
    schema={
        "name": "delete_artifact",
        "description": "Delete an artifact.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The filename of the artifact to delete"}
            },
            "required": ["name"],
        },
    },
    handler=lambda args, **kw: delete_artifact(name=args.get("name", "")),
    emoji="🗑️"
)
