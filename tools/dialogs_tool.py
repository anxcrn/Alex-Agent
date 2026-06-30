import os
import json
import time
import uuid
from pathlib import Path
from tools.registry import registry
from alex_constants import get_alex_home

def _get_dialogs_dir() -> Path:
    home = get_alex_home()
    dialogs_dir = Path(home) / "dialogs"
    dialogs_dir.mkdir(parents=True, exist_ok=True)
    return dialogs_dir

def _wait_for_dialog(dialog_id: str, timeout: int = 300) -> dict:
    """Blocks and polls the dialog file until it is resolved or times out."""
    dialogs_dir = _get_dialogs_dir()
    file_path = dialogs_dir / f"{dialog_id}.json"
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if data.get("status") == "resolved":
                    file_path.unlink(missing_ok=True)
                    return data
            except Exception:
                pass
        time.sleep(0.2)
        
    file_path.unlink(missing_ok=True)
    return {"status": "timeout", "error": "Dialog timed out waiting for response"}

def ask_question(question: str, options: list, is_multi_select: bool = False) -> str:
    """Ask the user a multiple choice question using a GUI modal."""
    dialog_id = uuid.uuid4().hex[:12]
    dialogs_dir = _get_dialogs_dir()
    file_path = dialogs_dir / f"{dialog_id}.json"
    
    payload = {
        "id": dialog_id,
        "type": "question",
        "status": "pending",
        "question": question,
        "options": options,
        "is_multi_select": is_multi_select,
        "created_at": time.time()
    }
    
    file_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    
    res = _wait_for_dialog(dialog_id)
    if res.get("status") == "resolved":
        return json.dumps({
            "success": True,
            "answer": res.get("answer")
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "error": res.get("error", "timeout")
        })

def ask_permission(reason: str, action: str, target: str) -> str:
    """Ask the user for permission to execute a specific action."""
    dialog_id = uuid.uuid4().hex[:12]
    dialogs_dir = _get_dialogs_dir()
    file_path = dialogs_dir / f"{dialog_id}.json"
    
    payload = {
        "id": dialog_id,
        "type": "permission",
        "status": "pending",
        "reason": reason,
        "action": action,
        "target": target,
        "created_at": time.time()
    }
    
    file_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    
    res = _wait_for_dialog(dialog_id)
    if res.get("status") == "resolved":
        return json.dumps({
            "success": True,
            "granted": res.get("granted", False)
        })
    else:
        return json.dumps({
            "success": False,
            "error": res.get("error", "timeout")
        })

registry.register(
    name="ask_question",
    toolset="dialogs",
    schema={
        "name": "ask_question",
        "description": "Ask the user a multiple choice question using a GUI modal dialog overlay.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to present to the user"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Predefined options for the user to choose from"
                },
                "is_multi_select": {
                    "type": "boolean",
                    "description": "Whether the user can select multiple options"
                }
            },
            "required": ["question", "options"],
        },
    },
    handler=lambda args, **kw: ask_question(
        question=args.get("question", ""),
        options=args.get("options", []),
        is_multi_select=args.get("is_multi_select", False)
    ),
    emoji="❓"
)

registry.register(
    name="ask_permission",
    toolset="dialogs",
    schema={
        "name": "ask_permission",
        "description": "Request the user's explicit permission before performing a sensitive or write operation.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "The reason why permission is needed"},
                "action": {"type": "string", "description": "The action being performed, e.g. 'write_file' or 'execute_command'"},
                "target": {"type": "string", "description": "The target of the action, e.g. path to file or command string"}
            },
            "required": ["reason", "action", "target"],
        },
    },
    handler=lambda args, **kw: ask_permission(
        reason=args.get("reason", ""),
        action=args.get("action", ""),
        target=args.get("target", "")
    ),
    emoji="🛡️"
)
