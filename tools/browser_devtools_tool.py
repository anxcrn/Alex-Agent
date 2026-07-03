#!/usr/bin/env python3
"""
Chrome DevTools Protocol (CDP) high-level wrappers for the Alex Agent.

Provides dedicated tools that mirror Chrome DevTools / "Inspect Element"
capabilities — DOM inspection, CSS editing, network monitoring, performance
profiling, cookie/storage management, element highlighting, code coverage,
screenshotting, breakpoints, and accessibility auditing.

Every tool is gated on CDP being available (same availability check as
``browser_cdp``). Tools use the CDP supervisor's persistent WebSocket when
possible for stateful operations (network capture, coverage, profiling),
falling back to fresh CDP connections for stateless queries.

CDP method reference: https://chromedevtools.github.io/devtools-protocol/
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

CDP_DOCS_URL = "https://chromedevtools.github.io/devtools-protocol/"

try:
    import websockets
    from websockets.exceptions import WebSocketException

    _WS_AVAILABLE = True
except ImportError:
    websockets = None
    WebSocketException = Exception
    _WS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    return asyncio.run(coro)


def _resolve_cdp_endpoint() -> str:
    try:
        from tools.browser_tool import _get_cdp_override
        return (_get_cdp_override() or "").strip()
    except Exception as exc:
        logger.debug("browser_devtools: failed to resolve CDP endpoint: %s", exc)
        return ""


def _get_supervisor(task_id: Optional[str] = None):
    """Return the active CDP supervisor for *task_id*, or None."""
    tid = task_id or "default"
    try:
        from tools.browser_supervisor import SUPERVISOR_REGISTRY
        return SUPERVISOR_REGISTRY.get(tid)
    except Exception:
        return None


def _get_page_session_id(task_id: Optional[str] = None) -> Optional[str]:
    """Return the page-level CDP session id from the supervisor, if available."""
    sup = _get_supervisor(task_id)
    if sup is None:
        return None
    with sup._state_lock:
        return sup._page_session_id


async def _cdp_call(
    ws_url: str,
    method: str,
    params: Dict[str, Any] = None,
    target_id: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Make a single stateless CDP call (no supervisor)."""
    assert websockets is not None
    async with websockets.connect(
        ws_url,
        max_size=50 * 1024 * 1024,
        open_timeout=timeout,
        close_timeout=5,
        ping_interval=None,
    ) as ws:
        next_id = 1
        session_id: Optional[str] = None

        if target_id:
            attach_id = next_id
            next_id += 1
            await ws.send(json.dumps({
                "id": attach_id,
                "method": "Target.attachToTarget",
                "params": {"targetId": target_id, "flatten": True},
            }))
            deadline = asyncio.get_running_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError(f"Timed out attaching to target {target_id}")
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                msg = json.loads(raw)
                if msg.get("id") == attach_id:
                    if "error" in msg:
                        raise RuntimeError(f"Target.attachToTarget failed: {msg['error']}")
                    session_id = msg.get("result", {}).get("sessionId")
                    if not session_id:
                        raise RuntimeError("Target.attachToTarget did not return a sessionId")
                    break

        call_id = next_id
        req: Dict[str, Any] = {"id": call_id, "method": method, "params": params or {}}
        if session_id:
            req["sessionId"] = session_id
        await ws.send(json.dumps(req))

        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for response to {method}")
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            if msg.get("id") == call_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error: {msg['error']}")
                return msg.get("result", {})


def _get_target_for_page(ws_url: str, timeout: float = 10.0) -> Optional[str]:
    """Discover the first page target's targetId via a fresh CDP connection."""
    try:
        result = _run_async(_cdp_call(ws_url, "Target.getTargets", timeout=timeout))
        targets = result.get("targetInfos", [])
        page = next((t for t in targets if t.get("type") == "page"), None)
        return page["targetId"] if page else None
    except Exception:
        return None


def _supervisor_evaluate(
    expression: str,
    return_by_value: bool = True,
    task_id: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Evaluate JS via supervisor (fast path when available)."""
    sup = _get_supervisor(task_id)
    if sup is not None:
        return sup.evaluate_runtime(
            expression,
            return_by_value=return_by_value,
            await_promise=True,
            timeout=timeout,
        )
    return {"ok": False, "error": "No supervisor available"}


def _supervisor_cdp(
    method: str,
    params: Dict[str, Any] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Send CDP command via supervisor (fast path when available)."""
    sup = _get_supervisor(task_id)
    if sup is None:
        return None
    loop = sup._loop
    if loop is None or not loop.is_running():
        return None
    effective_sid = session_id
    if effective_sid is None:
        with sup._state_lock:
            effective_sid = sup._page_session_id
    if not effective_sid:
        return None

    async def _do():
        return await sup._cdp(method, params, session_id=effective_sid, timeout=timeout)

    try:
        from agent.async_utils import safe_schedule_threadsafe
        fut = safe_schedule_threadsafe(_do(), loop)
        if fut is None:
            return None
        return fut.result(timeout=timeout + 1)
    except Exception:
        return None


def _stateless_cdp(
    method: str,
    params: Dict[str, Any] = None,
    target_id: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Make a stateless CDP call (no supervisor). Falls back to supervisor if available."""
    ws_url = _resolve_cdp_endpoint()
    if not ws_url:
        raise RuntimeError("No CDP endpoint available")
    return _run_async(_cdp_call(ws_url, method, params, target_id, timeout))


def _cdp_or_supervisor(
    method: str,
    params: Dict[str, Any] = None,
    task_id: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Try supervisor first, fall back to stateless CDP."""
    result = _supervisor_cdp(method, params, task_id=task_id, timeout=timeout)
    if result is not None:
        return result
    tid = _get_page_target_id(task_id, timeout)
    return _stateless_cdp(method, params, target_id=tid, timeout=timeout)


def _get_page_target_id(task_id: Optional[str] = None, timeout: float = 10.0) -> Optional[str]:
    """Get the page target ID for a task."""
    sup = _get_supervisor(task_id)
    if sup is not None:
        with sup._state_lock:
            for fid, frame in sup._frames.items():
                if not frame.parent_frame_id and not frame.is_oopif:
                    return fid
    ws_url = _resolve_cdp_endpoint()
    if ws_url:
        return _get_target_for_page(ws_url, timeout)
    return None


def _ensure_dom_enabled(task_id: Optional[str] = None) -> None:
    """Enable the DOM domain if not already enabled."""
    try:
        _cdp_or_supervisor("DOM.enable", task_id=task_id, timeout=5.0)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tool: browser_inspect_element
# ---------------------------------------------------------------------------

BROWSER_INSPECT_ELEMENT_SCHEMA = {
    "name": "browser_inspect_element",
    "description": (
        "Inspect a DOM element on the page using a CSS selector. Returns the "
        "element's tag name, attributes, computed styles, box model dimensions, "
        "text content, ARIA roles, and accessibility properties. Mirrors "
        "Chrome DevTools' Elements panel \"Inspect\" feature.\n\n"
        "Use this to understand the structure and styling of any element "
        "before editing it with browser_edit_dom or browser_edit_css."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector for the element to inspect (e.g. 'h1', '.class', '#id', 'div > p')."
            },
            "pseudo": {
                "type": "string",
                "description": "Optional pseudo-element to inspect (e.g. '::before', '::after').",
                "default": ""
            },
            "attributes": {
                "type": "boolean",
                "description": "Whether to return element attributes.",
                "default": True
            },
            "computed_styles": {
                "type": "boolean",
                "description": "Whether to return computed CSS styles.",
                "default": True
            },
            "box_model": {
                "type": "boolean",
                "description": "Whether to return box model dimensions.",
                "default": True
            },
        },
        "required": ["selector"],
    },
}


def browser_inspect_element(
    selector: str,
    pseudo: str = "",
    attributes: bool = True,
    computed_styles: bool = True,
    box_model: bool = True,
    task_id: Optional[str] = None,
) -> str:
    try:
        _ensure_dom_enabled(task_id)
        doc = _cdp_or_supervisor("DOM.getDocument", {"depth": 0}, task_id=task_id, timeout=10.0)
        root_node_id = doc.get("root", {}).get("nodeId")
        if root_node_id is None:
            return tool_error("Failed to get document root node")

        query_result = _cdp_or_supervisor(
            "DOM.querySelector",
            {"nodeId": root_node_id, "selector": selector},
            task_id=task_id,
            timeout=10.0,
        )
        element_node_id = query_result.get("nodeId")
        if element_node_id is None:
            return tool_error(f"No element found for selector: {selector}")

        push_result = _cdp_or_supervisor(
            "DOM.pushNodesByBackendIdsToFrontend",
            {"backendNodeIds": [element_node_id]},
            task_id=task_id,
            timeout=10.0,
        )

        resolved = _cdp_or_supervisor(
            "DOM.resolveNode",
            {"nodeId": element_node_id},
            task_id=task_id,
            timeout=10.0,
        )
        object_id = resolved.get("object", {}).get("objectId")

        detail = _cdp_or_supervisor(
            "DOM.getBoxModel",
            {"nodeId": element_node_id},
            task_id=task_id,
            timeout=10.0,
        )

        outer_html = _cdp_or_supervisor(
            "DOM.getOuterHTML",
            {"nodeId": element_node_id},
            task_id=task_id,
            timeout=10.0,
        )

        info = {}
        if resolved:
            obj = resolved.get("object", {})
            info["description"] = obj.get("description", "")
            info["type"] = obj.get("type", "")
            info["subtype"] = obj.get("subtype", "")

        if attributes and object_id:
            try:
                attrs_result = _supervisor_evaluate(
                    "(el) => { const m = {}; for (const a of el.attributes) m[a.name] = a.value; return m; }",
                    task_id=task_id,
                )
                if attrs_result.get("ok"):
                    info["attributes"] = attrs_result.get("result", {})
            except Exception:
                try:
                    attrs_cdp = _cdp_or_supervisor(
                        "DOM.getAttributes",
                        {"nodeId": element_node_id},
                        task_id=task_id,
                        timeout=10.0,
                    )
                    if attrs_cdp and "attributes" in attrs_cdp:
                        attrs_list = attrs_cdp["attributes"]
                        info["attributes"] = dict(
                            zip(attrs_list[::2], attrs_list[1::2])
                        )
                except Exception:
                    pass

        if computed_styles:
            try:
                styles_result = _cdp_or_supervisor(
                    "CSS.getComputedStyleForNode",
                    {"nodeId": element_node_id},
                    task_id=task_id,
                    timeout=10.0,
                )
                if styles_result and "computedStyle" in styles_result:
                    info["computed_styles"] = {
                        s["name"]: s["value"]
                        for s in styles_result["computedStyle"]
                    }
            except Exception:
                pass

        if box_model and detail and "model" in detail:
            model = detail["model"]
            info["box_model"] = {
                "content": model.get("content", []),
                "padding": model.get("padding", []),
                "border": model.get("border", []),
                "margin": model.get("margin", []),
                "width": model.get("width"),
                "height": model.get("height"),
            }

        if outer_html and "outerHTML" in outer_html:
            info["outer_html"] = outer_html["outerHTML"][:2000]

        if object_id:
            try:
                aria_result = _supervisor_evaluate(
                    f"""(() => {{
                        const el = document.querySelector({json.dumps(selector)});
                        if (!el) return null;
                        return {{
                            role: el.getAttribute('role') || el.role || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            ariaLabelledby: el.getAttribute('aria-labelledby') || '',
                            ariaDescribedby: el.getAttribute('aria-describedby') || '',
                            ariaHidden: el.getAttribute('aria-hidden') || '',
                            tabIndex: el.tabIndex,
                            accessibleName: el.getAttribute('aria-label') || el.title || el.alt || '',
                            tagName: el.tagName,
                            id: el.id,
                            className: el.className,
                            textContent: (el.textContent || '').trim().substring(0, 500),
                            innerText: (el.innerText || '').trim().substring(0, 500),
                            childElementCount: el.children.length,
                            isVisible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                        }};
                    }})()""",
                    task_id=task_id,
                )
                if aria_result.get("ok") and aria_result.get("result"):
                    info["element_info"] = aria_result["result"]
            except Exception:
                pass

        result_obj = {
            "success": True,
            "selector": selector,
            "node_id": element_node_id,
            "info": info,
        }
        return tool_result(result_obj)
    except Exception as exc:
        logger.exception("browser_inspect_element failed")
        return tool_error(
            f"Inspect element failed: {type(exc).__name__}: {exc}",
            selector=selector,
        )


# ---------------------------------------------------------------------------
# Tool: browser_edit_dom
# ---------------------------------------------------------------------------

BROWSER_EDIT_DOM_SCHEMA = {
    "name": "browser_edit_dom",
    "description": (
        "Edit the DOM of the current page — change innerHTML, set/remove "
        "attributes, delete elements. Mirrors Chrome DevTools' Elements panel "
        "edit-in-place functionality. Requires a CSS selector to target the element."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector for the target element."
            },
            "action": {
                "type": "string",
                "enum": ["set_inner_html", "set_outer_html", "set_attribute",
                         "remove_attribute", "delete_element", "set_text_content",
                         "set_style", "add_class", "remove_class"],
                "description": (
                    "Edit action to perform:\n"
                    "- set_inner_html: Replace inner HTML of the element\n"
                    "- set_outer_html: Replace the element itself with new HTML\n"
                    "- set_attribute: Set an attribute value\n"
                    "- remove_attribute: Remove an attribute\n"
                    "- delete_element: Remove the element from DOM\n"
                    "- set_text_content: Set text content (safe, no HTML parsing)\n"
                    "- set_style: Set a CSS property on the element's style attribute\n"
                    "- add_class: Add a CSS class\n"
                    "- remove_class: Remove a CSS class"
                ),
            },
            "value": {
                "type": "string",
                "description": "Value for the action (new HTML, attribute value, text content, CSS property value, class name, etc.). Required for: set_inner_html, set_outer_html, set_attribute, set_text_content, set_style, add_class, remove_class.",
                "default": ""
            },
            "attribute_name": {
                "type": "string",
                "description": "Attribute name for set_attribute/remove_attribute actions.",
                "default": ""
            },
            "style_property": {
                "type": "string",
                "description": "CSS property name for set_style action (e.g. 'color', 'background-color').",
                "default": ""
            },
        },
        "required": ["selector", "action"],
    },
}


def browser_edit_dom(
    selector: str,
    action: str,
    value: str = "",
    attribute_name: str = "",
    style_property: str = "",
    task_id: Optional[str] = None,
) -> str:
    valid_actions = {
        "set_inner_html", "set_outer_html", "set_attribute", "remove_attribute",
        "delete_element", "set_text_content", "set_style", "add_class", "remove_class",
    }
    if action not in valid_actions:
        return tool_error(
            f"Invalid action: {action}. Valid: {', '.join(sorted(valid_actions))}"
        )

    actions_requiring_value = {
        "set_inner_html", "set_outer_html", "set_attribute",
        "set_text_content", "set_style", "add_class", "remove_class",
    }
    if action in actions_requiring_value and not value:
        return tool_error(f"Action '{action}' requires a 'value' parameter")

    if action in ("set_attribute", "remove_attribute") and not attribute_name:
        return tool_error(f"Action '{action}' requires 'attribute_name' parameter")

    if action == "set_style" and not style_property:
        return tool_error("Action 'set_style' requires 'style_property' parameter")

    escaped_selector = json.dumps(selector)
    escaped_value = json.dumps(value)
    escaped_attr = json.dumps(attribute_name)
    escaped_style_prop = json.dumps(style_property)

    js_expr = ""
    if action == "set_inner_html":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.innerHTML = {escaped_value}; "
            f"return {{success: true, newLength: el.innerHTML.length}}; }})()"
        )
    elif action == "set_outer_html":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.outerHTML = {escaped_value}; "
            f"return {{success: true}}; }})()"
        )
    elif action == "set_attribute":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.setAttribute({escaped_attr}, {escaped_value}); "
            f"return {{success: true, attr: {escaped_attr}, value: {escaped_value}}}; }})()"
        )
    elif action == "remove_attribute":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.removeAttribute({escaped_attr}); "
            f"return {{success: true, removedAttr: {escaped_attr}}}; }})()"
        )
    elif action == "delete_element":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.remove(); "
            f"return {{success: true}}; }})()"
        )
    elif action == "set_text_content":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.textContent = {escaped_value}; "
            f"return {{success: true}}; }})()"
        )
    elif action == "set_style":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.style[{json.dumps(style_property)}] = {escaped_value}; "
            f"return {{success: true, property: {json.dumps(style_property)}, value: {escaped_value}}}; }})()"
        )
    elif action == "add_class":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.classList.add({escaped_value}); "
            f"return {{success: true, addedClass: {escaped_value}}}; }})()"
        )
    elif action == "remove_class":
        js_expr = (
            f"(function() {{ const el = document.querySelector({escaped_selector}); "
            f"if (!el) return {{error: 'Element not found'}}; "
            f"el.classList.remove({escaped_value}); "
            f"return {{success: true, removedClass: {escaped_value}}}; }})()"
        )

    try:
        result = _supervisor_evaluate(js_expr, task_id=task_id)
        if result.get("ok"):
            return tool_result({
                "success": True,
                "action": action,
                "selector": selector,
                "result": result.get("result", {}),
            })
        # Fall back to stateless CDP eval
        target_id = _get_page_target_id(task_id)
        ws_url = _resolve_cdp_endpoint()
        if not ws_url:
            return tool_error("No CDP endpoint available")
        cdp_result = _run_async(_cdp_call(
            ws_url,
            "Runtime.evaluate",
            {"expression": js_expr, "returnByValue": True, "awaitPromise": True},
            target_id=target_id,
            timeout=15.0,
        ))
        eval_result = cdp_result.get("result", {})
        exception = eval_result.get("exceptionDetails")
        if exception:
            return tool_error(f"JavaScript error: {exception.get('text', '')}")
        value = eval_result.get("value", {})
        if isinstance(value, dict) and value.get("error"):
            return tool_error(value["error"])
        return tool_result({
            "success": True,
            "action": action,
            "selector": selector,
            "result": value,
        })
    except Exception as exc:
        logger.exception("browser_edit_dom failed")
        return tool_error(f"DOM edit failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tool: browser_network
# ---------------------------------------------------------------------------

BROWSER_NETWORK_SCHEMA = {
    "name": "browser_network",
    "description": (
        "Capture, filter, and retrieve network request logs from the browser. "
        "Mirrors Chrome DevTools' Network panel. Can start/stop network "
        "capture, and retrieve captured requests/ responses. Use this to "
        "debug API calls, check resource loading, analyze XHR/fetch requests, "
        "and inspect response data."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "get_log", "clear"],
                "description": (
                    "- start: Begin capturing network requests\n"
                    "- stop: Stop capturing network requests\n"
                    "- get_log: Return captured request/response log\n"
                    "- clear: Clear the captured log"
                ),
            },
            "filter_type": {
                "type": "string",
                "enum": ["all", "xhr", "fetch", "script", "stylesheet", "image",
                         "font", "document", "media", "websocket", "other"],
                "description": "Filter by resource type (default: all). Only used with get_log.",
                "default": "all",
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum number of log entries to return (default: 50).",
                "default": 50,
            },
        },
        "required": ["action"],
    },
}

_network_capture_state: Dict[str, Dict[str, Any]] = {}


def browser_network(
    action: str,
    filter_type: str = "all",
    max_entries: int = 50,
    task_id: Optional[str] = None,
) -> str:
    tid = task_id or "default"

    try:
        if action == "start":
            _cdp_or_supervisor("Network.enable", {}, task_id=task_id, timeout=10.0)
            _network_capture_state[tid] = {
                "requests": [],
                "started_at": time.time(),
            }
            return tool_result({
                "success": True,
                "action": "start",
                "message": "Network capture started. Use browser_network action='get_log' to retrieve requests.",
            })

        elif action == "stop":
            try:
                _cdp_or_supervisor("Network.disable", task_id=task_id, timeout=10.0)
            except Exception:
                pass
            state = _network_capture_state.pop(tid, None)
            count = len(state["requests"]) if state else 0
            return tool_result({
                "success": True,
                "action": "stop",
                "captured_count": count,
                "message": "Network capture stopped.",
            })

        elif action == "clear":
            _network_capture_state.pop(tid, None)
            return tool_result({
                "success": True,
                "action": "clear",
                "message": "Network log cleared.",
            })

        elif action == "get_log":
            state = _network_capture_state.get(tid)
            entries = state["requests"] if state else []
            if filter_type != "all":
                entries = [e for e in entries if e.get("type") == filter_type]
            entries = entries[-max_entries:]
            url_filter = filter_type if filter_type != "all" else None
            return tool_result({
                "success": True,
                "action": "get_log",
                "captured_count": len(state["requests"]) if state else 0,
                "returned_count": len(entries),
                "filter_type": filter_type,
                "requests": entries,
            })

        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_network failed")
        return tool_error(f"Network operation failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tool: browser_performance
# ---------------------------------------------------------------------------

BROWSER_PERFORMANCE_SCHEMA = {
    "name": "browser_performance",
    "description": (
        "Start/stop CPU performance profiling and retrieve profiling results. "
        "Mirrors Chrome DevTools' Performance panel. Useful for identifying "
        "performance bottlenecks, measuring page load/rendering times, and "
        "analyzing JS execution time."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "get_metrics"],
                "description": (
                    "- start: Begin CPU performance profiling\n"
                    "- stop: Stop profiling and retrieve trace data\n"
                    "- get_metrics: Get current performance metrics (no profiling needed)"
                ),
            },
            "max_trace_entries": {
                "type": "integer",
                "description": "Maximum trace event entries to return when stopping (default: 200).",
                "default": 200,
            },
        },
        "required": ["action"],
    },
}

_perf_state: Dict[str, Dict[str, Any]] = {}


def browser_performance(
    action: str,
    max_trace_entries: int = 200,
    task_id: Optional[str] = None,
) -> str:
    try:
        if action == "start":
            _cdp_or_supervisor("Performance.enable", task_id=task_id, timeout=10.0)
            _perf_state[task_id or "default"] = {"started_at": time.time()}
            return tool_result({
                "success": True,
                "action": "start",
                "message": "Performance profiling started. Call browser_performance action='stop' to get results.",
            })

        elif action == "stop":
            _perf_state.pop(task_id or "default", None)
            try:
                _cdp_or_supervisor("Performance.disable", task_id=task_id, timeout=10.0)
            except Exception:
                pass
            return tool_result({
                "success": True,
                "action": "stop",
                "message": "Performance profiling stopped.",
            })

        elif action == "get_metrics":
            metrics_result = _cdp_or_supervisor(
                "Performance.getMetrics", task_id=task_id, timeout=10.0
            )
            if not metrics_result or "metrics" not in metrics_result:
                return _fallback_get_metrics(task_id)

            metrics_list = metrics_result["metrics"]
            metrics = {m["name"]: m["value"] for m in metrics_list}
            summary = {
                "timestamp": metrics.get("Timestamp", 0),
                "dom_nodes": int(metrics.get("DOMNodes", 0)),
                "dom_event_listeners": int(metrics.get("JSEventListeners", 0)),
                "js_heap_used_size": _format_bytes(metrics.get("JSHeapUsedSize", 0)),
                "js_heap_total_size": _format_bytes(metrics.get("JSHeapTotalSize", 0)),
                "layout_count": int(metrics.get("LayoutCount", 0)),
                "recalc_style_count": int(metrics.get("RecalcStyleCount", 0)),
                "nodes": int(metrics.get("Nodes", 0)),
                "documents": int(metrics.get("Documents", 0)),
                "frames": int(metrics.get("Frames", 0)),
                "script_duration": f"{metrics.get('ScriptDuration', 0):.2f}s",
                "layout_duration": f"{metrics.get('LayoutDuration', 0):.2f}s",
                "task_duration": f"{metrics.get('TaskDuration', 0):.2f}s",
            }
            return tool_result({
                "success": True,
                "action": "get_metrics",
                "metrics": summary,
                "all_metrics": metrics_list[:max_trace_entries],
            })
        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_performance failed")
        return tool_error(f"Performance operation failed: {type(exc).__name__}: {exc}")


def _fallback_get_metrics(task_id: Optional[str] = None) -> str:
    """Get performance metrics via JS evaluation as a fallback."""
    js = (
        "JSON.stringify({"
        "  domNodes: document.querySelectorAll('*').length,"
        "  scriptTags: document.querySelectorAll('script').length,"
        "  styleSheets: document.styleSheets.length,"
        "  documentHeight: document.documentElement.scrollHeight,"
        "  documentWidth: document.documentElement.scrollWidth,"
        "  title: document.title,"
        "  url: location.href,"
        "  loadTime: performance.timing ? "
        "    (performance.timing.loadEventEnd - performance.timing.navigationStart) : "
        "    null,"
        "  memory: performance.memory ? {"
        "    usedJSHeapSize: performance.memory.usedJSHeapSize,"
        "    totalJSHeapSize: performance.memory.totalJSHeapSize,"
        "    jsHeapSizeLimit: performance.memory.jsHeapSizeLimit"
        "  } : null,"
        "  timing: {"
        "    domContentLoaded: performance.getEntriesByType('navigation')[0]?."
        "      domContentLoadedEventEnd || null,"
        "    load: performance.getEntriesByType('navigation')[0]?."
        "      loadEventEnd || null,"
        "    domInteractive: performance.getEntriesByType('navigation')[0]?."
        "      domInteractive || null"
        "  },"
        "  paintTiming: performance.getEntriesByType('paint').map(e => ({"
        "    name: e.name, startTime: e.startTime"
        "  })),"
        "})"
    )
    result = _supervisor_evaluate(js, task_id=task_id)
    if result.get("ok"):
        raw = result.get("result", {})
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                pass
        return tool_result({
            "success": True,
            "action": "get_metrics",
            "metrics": raw if isinstance(raw, dict) else {"raw": raw},
        })
    return tool_error("Could not retrieve performance metrics")


def _format_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# ---------------------------------------------------------------------------
# Tool: browser_cookies
# ---------------------------------------------------------------------------

BROWSER_COOKIES_SCHEMA = {
    "name": "browser_cookies",
    "description": (
        "Get, set, or delete browser cookies. Mirrors Chrome DevTools' "
        "Application panel → Cookies section. Use this to inspect session "
        "cookies, authentication tokens, or modify cookies for testing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_all", "get_by_name", "set", "delete", "delete_all"],
                "description": (
                    "- get_all: Return all cookies for the current page/domain\n"
                    "- get_by_name: Get a specific cookie by name\n"
                    "- set: Create or update a cookie\n"
                    "- delete: Delete a specific cookie by name\n"
                    "- delete_all: Clear all cookies"
                ),
            },
            "name": {
                "type": "string",
                "description": "Cookie name. Required for: get_by_name, set, delete.",
                "default": ""
            },
            "value": {
                "type": "string",
                "description": "Cookie value. Required for: set.",
                "default": ""
            },
            "domain": {
                "type": "string",
                "description": "Cookie domain (defaults to current page domain). Used with: set.",
                "default": ""
            },
            "path": {
                "type": "string",
                "description": "Cookie path (default: '/'). Used with: set.",
                "default": "/"
            },
            "secure": {
                "type": "boolean",
                "description": "Whether the cookie is secure (default: false). Used with: set.",
                "default": False
            },
            "http_only": {
                "type": "boolean",
                "description": "Whether the cookie is HTTP-only (default: false). Used with: set.",
                "default": False
            },
        },
        "required": ["action"],
    },
}


def browser_cookies(
    action: str,
    name: str = "",
    value: str = "",
    domain: str = "",
    path: str = "/",
    secure: bool = False,
    http_only: bool = False,
    task_id: Optional[str] = None,
) -> str:
    try:
        if action == "get_all":
            result = _cdp_or_supervisor("Network.getAllCookies", task_id=task_id, timeout=10.0)
            if not result or "cookies" not in result:
                return _cookies_fallback(task_id)
            cookies = result["cookies"]
            return tool_result({
                "success": True,
                "count": len(cookies),
                "cookies": [
                    {
                        "name": c.get("name", ""),
                        "value": c.get("value", ""),
                        "domain": c.get("domain", ""),
                        "path": c.get("path", ""),
                        "secure": c.get("secure", False),
                        "http_only": c.get("httpOnly", False),
                        "same_site": c.get("sameSite", ""),
                        "session": c.get("session", True),
                        "expires": c.get("expires", 0),
                    }
                    for c in cookies
                ],
            })

        elif action == "get_by_name":
            if not name:
                return tool_error("'name' is required for get_by_name")
            result = _cdp_or_supervisor("Network.getAllCookies", task_id=task_id, timeout=10.0)
            if not result or "cookies" not in result:
                return _cookies_fallback(task_id, name)
            cookies = result["cookies"]
            match = next((c for c in cookies if c.get("name") == name), None)
            if not match:
                return tool_error(f"No cookie found with name: {name}")
            return tool_result({
                "success": True,
                "cookie": match,
            })

        elif action == "set":
            if not name or not value:
                return tool_error("'name' and 'value' are required for set")
            params = {
                "name": name,
                "value": value,
                "path": path or "/",
            }
            if domain:
                params["domain"] = domain
            if secure:
                params["secure"] = True
            if http_only:
                params["httpOnly"] = True
            set_result = _cdp_or_supervisor(
                "Network.setCookie", params, task_id=task_id, timeout=10.0
            )
            if not set_result:
                return _cookies_set_fallback(name, value, domain, path, secure, http_only, task_id)
            success = set_result.get("success", False)
            return tool_result({
                "success": success,
                "action": "set",
                "name": name,
                "value": value,
                "domain": domain or "current",
                "path": path,
            })

        elif action == "delete":
            if not name:
                return tool_error("'name' is required for delete")
            url = _get_page_url(task_id)
            delete_result = _cdp_or_supervisor(
                "Network.deleteCookies",
                {"name": name, "url": url} if url else {"name": name},
                task_id=task_id,
                timeout=10.0,
            )
            return tool_result({
                "success": True,
                "action": "delete",
                "name": name,
            })

        elif action == "delete_all":
            result = _cdp_or_supervisor("Network.getAllCookies", task_id=task_id, timeout=10.0)
            if result and "cookies" in result:
                for c in result["cookies"]:
                    try:
                        _cdp_or_supervisor(
                            "Network.deleteCookies",
                            {"name": c["name"], "url": _get_page_url(task_id)},
                            task_id=task_id,
                            timeout=5.0,
                        )
                    except Exception:
                        pass
            return tool_result({
                "success": True,
                "action": "delete_all",
                "message": "All cookies deleted.",
            })
        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_cookies failed")
        return tool_error(f"Cookie operation failed: {type(exc).__name__}: {exc}")


def _get_page_url(task_id: Optional[str] = None) -> str:
    result = _supervisor_evaluate("location.href", task_id=task_id)
    if result.get("ok"):
        return str(result.get("result", ""))
    return ""


def _cookies_fallback(task_id: Optional[str] = None, name: str = "") -> str:
    js = "JSON.stringify(document.cookie)"
    result = _supervisor_evaluate(js, task_id=task_id)
    if not result.get("ok"):
        return tool_error("Could not access cookies (CDP may not be connected)")
    raw = result.get("result", "")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            pass
    cookie_str = str(raw or "")
    if name:
        import urllib.parse
        parsed = urllib.parse.parse_qs(cookie_str.replace("; ", "&"))
        vals = parsed.get(name, [])
        if not vals:
            return tool_error(f"No cookie found with name: {name}")
        return tool_result({"success": True, "cookie": {"name": name, "value": vals[0]}})
    cookies = []
    for part in cookie_str.split("; "):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies.append({"name": k.strip(), "value": v.strip()})
    return tool_result({"success": True, "count": len(cookies), "cookies": cookies})


def _cookies_set_fallback(
    name: str, value: str, domain: str, path: str,
    secure: bool, http_only: bool, task_id: Optional[str] = None,
) -> str:
    parts = [f"{name}={value}"]
    if path:
        parts.append(f"path={path}")
    if domain:
        parts.append(f"domain={domain}")
    if secure:
        parts.append("secure")
    js = f"document.cookie = {json.dumps('; '.join(parts))}"
    result = _supervisor_evaluate(js, task_id=task_id)
    return tool_result({
        "success": result.get("ok", False),
        "action": "set",
        "name": name,
        "note": "Cookie set via document.cookie fallback" if result.get("ok") else "Failed to set cookie",
    })


# ---------------------------------------------------------------------------
# Tool: browser_storage
# ---------------------------------------------------------------------------

BROWSER_STORAGE_SCHEMA = {
    "name": "browser_storage",
    "description": (
        "Read, write, or clear browser local/session storage data. Mirrors "
        "Chrome DevTools' Application panel → Local Storage / Session Storage. "
        "Use this to inspect stored application state, tokens, or preferences."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "storage_type": {
                "type": "string",
                "enum": ["local_storage", "session_storage"],
                "description": "Which storage to access: local_storage (persists) or session_storage (per-tab).",
            },
            "action": {
                "type": "string",
                "enum": ["get_all", "get_item", "set_item", "remove_item", "clear"],
                "description": (
                    "- get_all: Return all key/value pairs\n"
                    "- get_item: Get a specific item by key\n"
                    "- set_item: Set a key/value pair\n"
                    "- remove_item: Remove a specific item\n"
                    "- clear: Clear all items"
                ),
            },
            "key": {
                "type": "string",
                "description": "Storage key. Required for: get_item, set_item, remove_item.",
                "default": ""
            },
            "value": {
                "type": "string",
                "description": "Value to set. Required for: set_item.",
                "default": ""
            },
        },
        "required": ["storage_type", "action"],
    },
}


def browser_storage(
    storage_type: str,
    action: str,
    key: str = "",
    value: str = "",
    task_id: Optional[str] = None,
) -> str:
    if storage_type not in ("local_storage", "session_storage"):
        return tool_error("storage_type must be 'local_storage' or 'session_storage'")

    storage_obj = "localStorage" if storage_type == "local_storage" else "sessionStorage"

    try:
        if action == "get_all":
            js = (
                f"JSON.stringify("
                f"  Object.entries({storage_obj}).reduce((acc, [k, v]) => "
                f"    {{...acc, [k]: v}}, {{}})"
                f")"
            )
            result = _supervisor_evaluate(js, task_id=task_id)
            if not result.get("ok"):
                return tool_error(f"Could not read {storage_type}")
            raw = result.get("result", {})
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    pass
            if not isinstance(raw, dict):
                return tool_result({"success": True, "count": 0, "items": {}})
            return tool_result({
                "success": True,
                "storage_type": storage_type,
                "count": len(raw),
                "items": raw,
            })

        elif action == "get_item":
            if not key:
                return tool_error("'key' is required for get_item")
            js = f"JSON.stringify({{key: {json.dumps(key)}, value: {storage_obj}.getItem({json.dumps(key)})}})"
            result = _supervisor_evaluate(js, task_id=task_id)
            if not result.get("ok"):
                return tool_error(f"Could not read {storage_type} item")
            raw = result.get("result", {})
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    pass
            return tool_result({
                "success": True,
                "storage_type": storage_type,
                "key": key,
                "value": raw.get("value") if isinstance(raw, dict) else None,
            })

        elif action == "set_item":
            if not key or value is None:
                return tool_error("'key' and 'value' are required for set_item")
            js = (
                f"(function() {{ "
                f"  {storage_obj}.setItem({json.dumps(key)}, {json.dumps(value)}); "
                f"  return 'ok'; "
                f"}})()"
            )
            _supervisor_evaluate(js, task_id=task_id)
            return tool_result({
                "success": True,
                "action": "set_item",
                "storage_type": storage_type,
                "key": key,
            })

        elif action == "remove_item":
            if not key:
                return tool_error("'key' is required for remove_item")
            js = (
                f"(function() {{ "
                f"  {storage_obj}.removeItem({json.dumps(key)}); "
                f"  return 'ok'; "
                f"}})()"
            )
            _supervisor_evaluate(js, task_id=task_id)
            return tool_result({
                "success": True,
                "action": "remove_item",
                "storage_type": storage_type,
                "key": key,
            })

        elif action == "clear":
            js = f"(function() {{ {storage_obj}.clear(); return 'ok'; }})()"
            _supervisor_evaluate(js, task_id=task_id)
            return tool_result({
                "success": True,
                "action": "clear",
                "storage_type": storage_type,
                "message": f"{storage_type} cleared.",
            })

        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_storage failed")
        return tool_error(f"Storage operation failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tool: browser_highlight
# ---------------------------------------------------------------------------

BROWSER_HIGHLIGHT_SCHEMA = {
    "name": "browser_highlight",
    "description": (
        "Visually highlight or dehighlight element(s) on the page by CSS "
        "selector. Mirrors Chrome DevTools' element hover/inspect highlighting. "
        "Useful for visually identifying elements before interacting with them "
        "or to confirm the correct element is targeted."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector for the element(s) to highlight."
            },
            "action": {
                "type": "string",
                "enum": ["highlight", "dehighlight", "dehighlight_all"],
                "description": (
                    "- highlight: Add a colored outline to the element\n"
                    "- dehighlight: Remove highlight from the element\n"
                    "- dehighlight_all: Remove all highlights"
                ),
            },
            "color": {
                "type": "string",
                "description": "CSS border color for highlight (default: 'red'). Examples: 'red', '#ff0000', 'rgba(255,0,0,0.5)'.",
                "default": "red"
            },
            "style": {
                "type": "string",
                "description": "Highlight style: 'outline' (default), 'border', 'background', 'box_shadow'.",
                "default": "outline"
            },
            "duration": {
                "type": "number",
                "description": "Auto-dehighlight after N seconds (0 = permanent, default: 5).",
                "default": 5
            },
        },
        "required": ["selector", "action"],
    },
}


_browser_highlight_count = 0


def browser_highlight(
    selector: str,
    action: str,
    color: str = "red",
    style: str = "outline",
    duration: int = 5,
    task_id: Optional[str] = None,
) -> str:
    global _browser_highlight_count

    try:
        if action == "highlight":
            _browser_highlight_count += 1
            h_id = _browser_highlight_count
            style_map = {
                "outline": f"outline: 3px solid {color} !important; outline-offset: 2px !important;",
                "border": f"border: 3px solid {color} !important;",
                "background": f"background-color: {color} !important;",
                "box_shadow": f"box-shadow: 0 0 0 3px {color}, 0 0 8px {color} !important;",
            }
            css_style = style_map.get(style, style_map["outline"])
            js = (
                f"(function() {{ "
                f"  const els = document.querySelectorAll({json.dumps(selector)}); "
                f"  if (!els.length) return {{count: 0}}; "
                f"  const tag = '__alex_highlight_{h_id}'; "
                f"  els.forEach(el => {{ el.setAttribute(tag, '1'); el.style.cssText += {json.dumps(css_style)}; }}); "
                f"  return {{count: els.length, highlight_id: {h_id}}}; "
                f"}})()"
            )
            result = _supervisor_evaluate(js, task_id=task_id)
            count = 0
            if result.get("ok"):
                r = result.get("result", {})
                if isinstance(r, dict):
                    count = r.get("count", 0)

            if duration > 0:
                import threading
                def _dehighlight():
                    try:
                        js_clear = (
                            f"(function() {{ "
                            f"  const els = document.querySelectorAll({json.dumps(selector)}); "
                            f"  const tag = '__alex_highlight_{h_id}'; "
                            f"  els.forEach(el => el.removeAttribute(tag)); "
                            f"  return 'ok'; "
                            f"}})()"
                        )
                        _supervisor_evaluate(js_clear, task_id=task_id)
                    except Exception:
                        pass
                threading.Timer(duration, _dehighlight).start()

            return tool_result({
                "success": True,
                "action": "highlight",
                "selector": selector,
                "highlight_count": count,
                "highlight_id": h_id,
                "auto_dehighlight_after_s": duration if duration > 0 else "manual",
            })

        elif action == "dehighlight":
            js = (
                f"(function() {{ "
                f"  const els = document.querySelectorAll({json.dumps(selector)}); "
                f"  for (let i = 0; i < 10; i++) {{ "
                f"    const attr = `__alex_highlight_${{i}}`; "
                f"    els.forEach(el => el.removeAttribute(attr)); "
                f"  }} "
                f"  return {{count: els.length}}; "
                f"}})()"
            )
            result = _supervisor_evaluate(js, task_id=task_id)
            return tool_result({
                "success": True,
                "action": "dehighlight",
                "selector": selector,
            })

        elif action == "dehighlight_all":
            js = (
                "(function() { "
                "  const all = document.querySelectorAll('*'); "
                "  for (let i = 0; i < 10; i++) { "
                "    const attr = `__alex_highlight_${i}`; "
                "    all.forEach(el => el.removeAttribute(attr)); "
                "  } "
                "  return 'ok'; "
                "})()"
            )
            _supervisor_evaluate(js, task_id=task_id)
            return tool_result({
                "success": True,
                "action": "dehighlight_all",
            })

        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_highlight failed")
        return tool_error(f"Highlight operation failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tool: browser_screenshot
# ---------------------------------------------------------------------------

BROWSER_SCREENSHOT_SCHEMA = {
    "name": "browser_screenshot",
    "description": (
        "Capture a screenshot of the page or a specific element. Mirrors "
        "Chrome DevTools' screenshot capability. Returns a base64-encoded PNG "
        "image. Use this to visually verify page state, capture element "
        "appearance, or create page snapshots."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["full_page", "viewport", "element"],
                "description": (
                    "- full_page: Screenshot the entire page (scrolling if needed)\n"
                    "- viewport: Screenshot only the visible viewport\n"
                    "- element: Screenshot a specific element"
                ),
                "default": "viewport"
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for element screenshot mode.",
                "default": ""
            },
            "format": {
                "type": "string",
                "enum": ["png", "jpeg"],
                "description": "Image format.",
                "default": "png"
            },
            "quality": {
                "type": "integer",
                "description": "JPEG quality (0-100, only for JPEG format).",
                "default": 80
            },
        },
        "required": [],
    },
}


def browser_screenshot(
    mode: str = "viewport",
    selector: str = "",
    format: str = "png",
    quality: int = 80,
    task_id: Optional[str] = None,
) -> str:
    try:
        if mode == "full_page":
            metrics = _cdp_or_supervisor(
                "Page.getLayoutMetrics", task_id=task_id, timeout=10.0
            )
            if not metrics:
                return tool_error("Could not get page layout metrics")
            content_size = metrics.get("contentSize", {})
            width = int(content_size.get("width", 1280))
            height = int(content_size.get("height", 720))

            _cdp_or_supervisor(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": min(width, 2560),
                    "height": min(height, 10000),
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
                task_id=task_id,
                timeout=10.0,
            )

            screenshot_result = _cdp_or_supervisor(
                "Page.captureScreenshot",
                {
                    "format": format,
                    "quality": quality if format == "jpeg" else None,
                    "fromSurface": True,
                    "captureBeyondViewport": True,
                },
                task_id=task_id,
                timeout=30.0,
            )

            _cdp_or_supervisor(
                "Emulation.clearDeviceMetricsOverride",
                task_id=task_id,
                timeout=5.0,
            )

        elif mode == "element":
            if not selector:
                return tool_error("'selector' is required for element screenshot mode")
            js = (
                f"(function() {{ "
                f"  const el = document.querySelector({json.dumps(selector)}); "
                f"  if (!el) return null; "
                f"  const r = el.getBoundingClientRect(); "
                f"  return {{x: r.x, y: r.y, width: r.width, height: r.height}}; "
                f"}})()"
            )
            result = _supervisor_evaluate(js, task_id=task_id)
            if not result.get("ok") or not result.get("result"):
                return tool_error(f"Element not found: {selector}")
            rect = result["result"]
            if isinstance(rect, str):
                try:
                    rect = json.loads(rect)
                except Exception:
                    pass
            if not isinstance(rect, dict):
                return tool_error(f"Could not get bounding rect for {selector}")
            clip = {
                "x": max(0, rect.get("x", 0)),
                "y": max(0, rect.get("y", 0)),
                "width": max(1, rect.get("width", 100)),
                "height": max(1, rect.get("height", 100)),
                "scale": 1,
            }
            screenshot_result = _cdp_or_supervisor(
                "Page.captureScreenshot",
                {
                    "format": format,
                    "quality": quality if format == "jpeg" else None,
                    "clip": clip,
                    "fromSurface": True,
                },
                task_id=task_id,
                timeout=30.0,
            )

        else:
            screenshot_result = _cdp_or_supervisor(
                "Page.captureScreenshot",
                {
                    "format": format,
                    "quality": quality if format == "jpeg" else None,
                    "fromSurface": True,
                },
                task_id=task_id,
                timeout=30.0,
            )

        if not screenshot_result or "data" not in screenshot_result:
            return tool_error("Screenshot capture failed")
        data = screenshot_result["data"]
        size_bytes = int(len(data) * 0.75)  # approximate base64 decoded size
        return tool_result({
            "success": True,
            "mode": mode,
            "format": format,
            "data": data,
            "size_bytes": size_bytes,
            "size_display": _format_bytes(size_bytes),
        })
    except Exception as exc:
        logger.exception("browser_screenshot failed")
        return tool_error(f"Screenshot failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tool: browser_breakpoint
# ---------------------------------------------------------------------------

BROWSER_BREAKPOINT_SCHEMA = {
    "name": "browser_breakpoint",
    "description": (
        "Set, remove, list, or manage JavaScript breakpoints. Mirrors Chrome "
        "DevTools' Sources panel → Breakpoints. Use this for debugging "
        "JavaScript execution — pause on specific lines, inspect variables, "
        "and step through code."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["set", "remove", "list", "remove_all", "set_event_listener"],
                "description": (
                    "- set: Set a breakpoint at a specific source location\n"
                    "- remove: Remove a breakpoint\n"
                    "- list: List all active breakpoints\n"
                    "- remove_all: Remove all breakpoints\n"
                    "- set_event_listener: Pause on specific event types"
                ),
            },
            "url": {
                "type": "string",
                "description": "URL or path of the script file. Required for: set, remove.",
                "default": ""
            },
            "line_number": {
                "type": "integer",
                "description": "1-based line number in the script. Required for: set.",
                "default": 0
            },
            "condition": {
                "type": "string",
                "description": "Optional breakpoint condition (JavaScript expression). Used with: set.",
                "default": ""
            },
            "event_name": {
                "type": "string",
                "description": "Event name for set_event_listener (e.g. 'click', 'keydown', 'scroll', 'load').",
                "default": ""
            },
        },
        "required": ["action"],
    },
}


_breakpoint_state: Dict[str, List[Dict[str, Any]]] = {}


def browser_breakpoint(
    action: str,
    url: str = "",
    line_number: int = 0,
    condition: str = "",
    event_name: str = "",
    task_id: Optional[str] = None,
) -> str:
    tid = task_id or "default"

    try:
        if action == "set":
            if not url or line_number < 1:
                return tool_error("'url' and 'line_number' (>= 1) are required for set")
            line_0 = line_number - 1
            bp_params: Dict[str, Any] = {
                "location": {
                    "url": url,
                    "lineNumber": line_0,
                }
            }
            if condition:
                bp_params["condition"] = condition
            result = _cdp_or_supervisor(
                "Debugger.setBreakpointByUrl",
                bp_params,
                task_id=task_id,
                timeout=10.0,
            )
            if not result or "breakpointId" not in result:
                return tool_error("Failed to set breakpoint (Debugger may not be enabled)")
            bp = {
                "id": result["breakpointId"],
                "url": url,
                "line_number": line_number,
                "condition": condition or None,
            }
            if tid not in _breakpoint_state:
                _breakpoint_state[tid] = []
            _breakpoint_state[tid].append(bp)
            locations = result.get("locations", [])
            return tool_result({
                "success": True,
                "action": "set",
                "breakpoint": bp,
                "resolved_locations": [
                    {"url": l.get("url", ""), "line": (l.get("lineNumber", 0) or 0) + 1}
                    for l in locations
                ],
            })

        elif action == "remove":
            if not url or line_number < 1:
                return tool_error("'url' and 'line_number' are required for remove")
            if tid in _breakpoint_state:
                _breakpoint_state[tid] = [
                    bp for bp in _breakpoint_state[tid]
                    if not (bp["url"] == url and bp["line_number"] == line_number)
                ]
            return tool_result({
                "success": True,
                "action": "remove",
                "url": url,
                "line_number": line_number,
            })

        elif action == "list":
            bps = _breakpoint_state.get(tid, [])
            return tool_result({
                "success": True,
                "action": "list",
                "count": len(bps),
                "breakpoints": bps,
            })

        elif action == "remove_all":
            _breakpoint_state.pop(tid, None)
            return tool_result({
                "success": True,
                "action": "remove_all",
            })

        elif action == "set_event_listener":
            if not event_name:
                return tool_error("'event_name' is required for set_event_listener")
            js = (
                f"(function() {{ "
                f"  let paused = false; "
                f"  const handler = (e) => {{ "
                f"    if (paused) return; "
                f"    paused = true; "
                f"    console.log('ALEX_DEBUG_EVENT:', {json.dumps(event_name)}, e.type); "
                f"    debugger; "
                f"  }}; "
                f"  document.addEventListener({json.dumps(event_name)}, handler, true); "
                f"  return 'listener_added'; "
                f"}})()"
            )
            _supervisor_evaluate(js, task_id=task_id)
            return tool_result({
                "success": True,
                "action": "set_event_listener",
                "event_name": event_name,
                "message": f"Debugger will pause on '{event_name}' events",
            })

        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_breakpoint failed")
        return tool_error(f"Breakpoint operation failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tool: browser_accessibility
# ---------------------------------------------------------------------------

BROWSER_ACCESSIBILITY_SCHEMA = {
    "name": "browser_accessibility",
    "description": (
        "Audit and inspect the accessibility tree of the page or a specific "
        "element. Mirrors Chrome DevTools' Accessibility panel. Returns "
        "ARIA roles, accessible names/descriptions, keyboard interaction "
        "info, and potential accessibility issues."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["page_audit", "inspect_element", "get_full_tree"],
                "description": (
                    "- page_audit: Run an accessibility audit on the page (checks for common issues)\n"
                    "- inspect_element: Get accessibility info for a specific element by selector\n"
                    "- get_full_tree: Get the full accessibility tree (can be large)"
                ),
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for inspect_element action.",
                "default": ""
            },
        },
        "required": ["action"],
    },
}


def browser_accessibility(
    action: str,
    selector: str = "",
    task_id: Optional[str] = None,
) -> str:
    try:
        if action == "page_audit":
            js = (
                "(function() { "
                "  const issues = []; "
                "  const all = document.querySelectorAll('*'); "
                "  const seenIds = new Set(); "
                "  all.forEach(el => { "
                "    if (el.id && seenIds.has(el.id)) "
                "      issues.push({type: 'duplicate_id', severity: 'warning', "
                "        message: `Duplicate ID: ${el.id}`, tag: el.tagName}); "
                "    if (el.id) seenIds.add(el.id); "
                "    if (el.tagName === 'IMG' && !el.alt && el.alt !== '') "
                "      issues.push({type: 'missing_alt', severity: 'error', "
                "        message: 'Image missing alt text', tag: 'IMG', "
                "        source: el.src ? el.src.substring(0, 100) : '' }); "
                "    if (el.tagName === 'A' && !el.getAttribute('aria-label') "
                "        && !el.textContent.trim()) "
                "      issues.push({type: 'empty_link', severity: 'warning', "
                "        message: 'Link with no accessible name', "
                "        href: el.href ? el.href.substring(0, 100) : '' }); "
                "    if (el.tagName === 'BUTTON' && !el.textContent.trim() "
                "        && !el.getAttribute('aria-label')) "
                "      issues.push({type: 'empty_button', severity: 'error', "
                "        message: 'Button with no accessible name' }); "
                "    if (el.getAttribute('role') && !['button','link','heading',"
                "        'img','list','listitem','navigation','banner','main',"
                "        'complementary','contentinfo','region','form','search',"
                "        'dialog','alert','status','timer','progressbar','tab',"
                "        'tabpanel','tablist','menu','menuitem','tree','grid'].includes(el.getAttribute('role'))) "
                "      issues.push({type: 'uncommon_role', severity: 'info', "
                "        message: `Uncommon ARIA role: ${el.getAttribute('role')}`, "
                "        tag: el.tagName }); "
                "    if (el.getAttribute('aria-hidden') === 'true' "
                "        && el.querySelector('[tabindex]')) "
                "      issues.push({type: 'focusable_hidden', severity: 'error', "
                "        message: 'Focusable element inside aria-hidden' }); "
                "  }); "
                "  const headings = document.querySelectorAll('h1,h2,h3,h4,h5,h6'); "
                "  const h1s = document.querySelectorAll('h1'); "
                "  if (h1s.length === 0) "
                "    issues.push({type: 'no_h1', severity: 'warning', "
                "      message: 'Page has no h1 heading' }); "
                "  if (headings.length > 0) { "
                "    let prev = 0; "
                "    headings.forEach(h => { "
                "      const level = parseInt(h.tagName[1]); "
                "      if (level - prev > 1) "
                "        issues.push({type: 'heading_skip', severity: 'warning', "
                "          message: `Heading level skipped from h${prev} to h${level}` }); "
                "      prev = level; "
                "    }); "
                "  } "
                "  if (!document.querySelector('main, [role=\"main\"]')) "
                "    issues.push({type: 'no_main', severity: 'info', "
                "      message: 'Page has no main landmark' }); "
                "  if (!document.querySelector('nav, [role=\"navigation\"]')) "
                "    issues.push({type: 'no_nav', severity: 'info', "
                "      message: 'Page has no navigation landmark' }); "
                "  const total = all.length; "
                "  const ariaEls = document.querySelectorAll('[aria-*]'); "
                "  return JSON.stringify({totalElements: total, "
                "    ariaElements: ariaEls.length, issues}); "
                "})()"
            )
            result = _supervisor_evaluate(js, task_id=task_id)
            if not result.get("ok"):
                return tool_error("Could not run accessibility audit")
            raw = result.get("result", "{}")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    pass
            return tool_result({
                "success": True,
                "action": "page_audit",
                "audit": raw if isinstance(raw, dict) else {"raw": str(raw)},
            })

        elif action == "inspect_element":
            if not selector:
                return tool_error("'selector' is required for inspect_element")
            js = (
                f"(function() {{ "
                f"  const el = document.querySelector({json.dumps(selector)}); "
                f"  if (!el) return null; "
                f"  const computed = window.getComputedStyle(el); "
                f"  return {{"
                f"    tagName: el.tagName,"
                f"    id: el.id,"
                f"    className: el.className,"
                f"    role: el.getAttribute('role') || '',"
                f"    ariaLabel: el.getAttribute('aria-label') || '',"
                f"    ariaLabelledby: el.getAttribute('aria-labelledby') || '',"
                f"    ariaDescribedby: el.getAttribute('aria-describedby') || '',"
                f"    ariaHidden: el.getAttribute('aria-hidden') || '',"
                f"    ariaExpanded: el.getAttribute('aria-expanded') || '',"
                f"    ariaPressed: el.getAttribute('aria-pressed') || '',"
                f"    ariaCurrent: el.getAttribute('aria-current') || '',"
                f"    ariaDisabled: el.getAttribute('aria-disabled') || '',"
                f"    tabIndex: el.tabIndex,"
                f"    accessibleName: el.getAttribute('aria-label') || el.title || el.alt || '',"
                f"    textContent: (el.textContent || '').trim().substring(0, 300),"
                f"    isFocusable: el.tabIndex >= 0 || "
                f"      ['A','BUTTON','INPUT','SELECT','TEXTAREA'].includes(el.tagName),"
                f"    isVisible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),"
                f"    hasOnClick: typeof el.onclick === 'function' || "
                f"      el.hasAttribute('onclick'),"
                f"    childElementCount: el.children.length,"
                f"    backgroundColor: computed.backgroundColor,"
                f"    color: computed.color,"
                f"    fontSize: computed.fontSize,"
                f"    cursor: computed.cursor,"
                f"  }}; "
                f"}})()"
            )
            result = _supervisor_evaluate(js, task_id=task_id)
            if not result.get("ok") or not result.get("result"):
                return tool_error(f"Element not found: {selector}")
            return tool_result({
                "success": True,
                "action": "inspect_element",
                "selector": selector,
                "accessibility": result["result"],
            })

        elif action == "get_full_tree":
            try:
                _ensure_dom_enabled(task_id)
                axtree = _cdp_or_supervisor(
                    "Accessibility.getFullAXTree",
                    {},
                    task_id=task_id,
                    timeout=15.0,
                )
                if axtree and "nodes" in axtree:
                    nodes = axtree["nodes"]
                    summary = {
                        "total_nodes": len(nodes),
                        "roles": {},
                    }
                    for node in nodes:
                        role = node.get("role", {}).get("value", "unknown")
                        summary["roles"][role] = summary["roles"].get(role, 0) + 1
                    sample = [
                        {
                            "node_id": n.get("nodeId"),
                            "role": n.get("role", {}).get("value", ""),
                            "name": n.get("name", {}).get("value", ""),
                            "description": n.get("description", {}).get("value", ""),
                        }
                        for n in nodes[:30]
                        if n.get("role", {}).get("value") not in ("", "Generic", "InlineTextBox")
                    ]
                    return tool_result({
                        "success": True,
                        "action": "get_full_tree",
                        "summary": summary,
                        "sample_nodes": sample,
                        "truncated": len(nodes) > 30,
                    })
            except Exception:
                pass
            # Fallback: get tree via JS
            js = (
                "(function() { "
                "  const all = document.querySelectorAll('*'); "
                "  const nodes = []; "
                "  all.forEach(el => { "
                "    const role = el.getAttribute('role') || ''; "
                "    if (role) { "
                "      nodes.push({"
                "        tag: el.tagName, role, "
                "        name: el.getAttribute('aria-label') || el.title || el.alt || '', "
                "        id: el.id, "
                "        classes: el.className.substring(0, 50)"
                "      }); "
                "    } "
                "  }); "
                "  return JSON.stringify(nodes.slice(0, 50)); "
                "})()"
            )
            result = _supervisor_evaluate(js, task_id=task_id)
            if not result.get("ok"):
                return tool_error("Could not get accessibility tree")
            raw = result.get("result", "[]")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    pass
            return tool_result({
                "success": True,
                "action": "get_full_tree",
                "nodes": raw if isinstance(raw, list) else [],
                "note": "Limited to elements with explicit ARIA roles (fallback method)",
            })

        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_accessibility failed")
        return tool_error(f"Accessibility operation failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tool: browser_coverage
# ---------------------------------------------------------------------------

BROWSER_COVERAGE_SCHEMA = {
    "name": "browser_coverage",
    "description": (
        "Start, stop, or retrieve JavaScript and CSS code coverage data. "
        "Mirrors Chrome DevTools' Coverage panel (the \"Reload and record "
        "coverage\" + \"Coverage\" tabs). Use this to find unused CSS/JS "
        "code and identify opportunities to reduce page size."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "get_results"],
                "description": (
                    "- start: Begin recording JS + CSS coverage\n"
                    "- stop: Stop recording and return coverage data\n"
                    "- get_results: Poll current coverage results without stopping"
                ),
            },
            "reset_on_start": {
                "type": "boolean",
                "description": "Reset coverage data before starting (default: true).",
                "default": True
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum coverage entries to return (default: 50).",
                "default": 50
            },
        },
        "required": ["action"],
    },
}

_coverage_state: Dict[str, Dict[str, Any]] = {}


def browser_coverage(
    action: str,
    reset_on_start: bool = True,
    max_entries: int = 50,
    task_id: Optional[str] = None,
) -> str:
    tid = task_id or "default"

    try:
        if action == "start":
            if reset_on_start:
                try:
                    _cdp_or_supervisor("CSS.stopRuleUsageTracking", task_id=task_id, timeout=5.0)
                except Exception:
                    pass
            _cdp_or_supervisor("CSS.startRuleUsageTracking", task_id=task_id, timeout=10.0)
            _coverage_state[tid] = {"started_at": time.time()}
            return tool_result({
                "success": True,
                "action": "start",
                "message": "Coverage recording started. Navigate/interact with the page, then call browser_coverage action='stop'.",
            })

        elif action in ("stop", "get_results"):
            state = _coverage_state.get(tid)
            if action == "stop":
                _coverage_state.pop(tid, None)

            coverage_entries = []

            try:
                css_result = _cdp_or_supervisor(
                    "CSS.takeCoverageDelta", task_id=task_id, timeout=15.0
                )
                if css_result and "coverage" in css_result:
                    coverage_entries.extend(css_result["coverage"])
            except Exception:
                pass

            try:
                _cdp_or_supervisor(
                    "Profiler.enable", task_id=task_id, timeout=5.0
                )
                js_result = _cdp_or_supervisor(
                    "Profiler.takePreciseCoverage", task_id=task_id, timeout=15.0
                )
                if js_result and "result" in js_result:
                    for entry in js_result["result"]:
                        coverage_entries.append({
                            "url": entry.get("url", ""),
                            "ranges": entry.get("ranges", []),
                            "type": "script",
                            "functions": entry.get("functions", []),
                        })
                try:
                    _cdp_or_supervisor("Profiler.disable", task_id=task_id, timeout=5.0)
                except Exception:
                    pass
            except Exception:
                pass

            if action == "stop":
                try:
                    _cdp_or_supervisor("CSS.stopRuleUsageTracking", task_id=task_id, timeout=5.0)
                except Exception:
                    pass

            if not coverage_entries:
                return tool_result({
                    "success": True,
                    "action": action,
                    "entries": [],
                    "summary": {
                        "total_bytes": 0,
                        "used_bytes": 0,
                        "unused_bytes": 0,
                        "unused_percentage": 0,
                    },
                    "message": "No coverage data available. Try navigating to a page first.",
                })

            processed = _process_coverage_entries(coverage_entries)
            entries = processed["entries"][-max_entries:]

            return tool_result({
                "success": True,
                "action": action,
                "entry_count": len(coverage_entries),
                "returned_count": len(entries),
                "entries": entries,
                "summary": processed["summary"],
            })

        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_coverage failed")
        return tool_error(f"Coverage operation failed: {type(exc).__name__}: {exc}")


def _process_coverage_entries(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    processed = []
    total_bytes = 0
    used_bytes = 0

    for entry in entries:
        url = entry.get("url", "") or entry.get("styleSheetURL", "")
        if not url:
            continue
        ranges = entry.get("ranges", [])
        entry_type = entry.get("type", "stylesheet")
        total = sum(r.get("endOffset", 0) - r.get("startOffset", 0) for r in ranges)
        used = sum(r.get("endOffset", 0) - r.get("startOffset", 0) for r in ranges if r.get("used", False))
        unused = total - used
        total_bytes += total
        used_bytes += used
        processed.append({
            "url": url[:200],
            "type": entry_type,
            "total_size": total,
            "used_size": used,
            "unused_size": unused,
            "ranges_count": len(ranges),
        })

    unused_bytes = total_bytes - used_bytes
    unused_pct = round((unused_bytes / total_bytes * 100), 1) if total_bytes > 0 else 0

    return {
        "entries": processed,
        "summary": {
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "unused_bytes": unused_bytes,
            "unused_percentage": unused_pct,
        },
    }


# ---------------------------------------------------------------------------
# Tool: browser_console
# (Enhanced version — already exists in browser_tool.py but we register
#  a devtools-specific version with extra filtering/analysis capabilities)
# ---------------------------------------------------------------------------

BROWSER_CONSOLE_DEVTOOLS_SCHEMA = {
    "name": "browser_console_advanced",
    "description": (
        "Advanced browser console operations — get filtered console logs, "
        "evaluate JavaScript, monitor specific events, or clear console output. "
        "Enhanced version of the basic browser_console tool with support for "
        "console history filtering, preserving logs across navigations, and "
        "capturing structured console data (warnings, errors, debug, etc.)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_logs", "evaluate", "clear", "monitor", "get_exceptions"],
                "description": (
                    "- get_logs: Retrieve accumulated console logs with optional filtering\n"
                    "- evaluate: Execute JavaScript in the browser console\n"
                    "- clear: Clear console output\n"
                    "- monitor: Start/stop monitoring a specific event type\n"
                    "- get_exceptions: Get only JavaScript exceptions/errors"
                ),
            },
            "expression": {
                "type": "string",
                "description": "JavaScript expression to evaluate (required for action='evaluate').",
                "default": ""
            },
            "filter_level": {
                "type": "string",
                "enum": ["all", "error", "warning", "info", "debug", "exception"],
                "description": "Filter logs by level (default: all). Used with get_logs and get_exceptions.",
                "default": "all"
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum log entries to return (default: 100).",
                "default": 100
            },
            "monitor_event": {
                "type": "string",
                "description": "Event type to monitor (e.g. 'click', 'scroll', 'resize', 'error'). Used with monitor action.",
                "default": ""
            },
            "monitor_action": {
                "type": "string",
                "enum": ["start", "stop"],
                "description": "Start or stop monitoring. Used with monitor action.",
                "default": "start"
            },
        },
        "required": ["action"],
    },
}

_console_monitor_state: Dict[str, bool] = {}


def browser_console_advanced(
    action: str,
    expression: str = "",
    filter_level: str = "all",
    max_entries: int = 100,
    monitor_event: str = "",
    monitor_action: str = "start",
    task_id: Optional[str] = None,
) -> str:
    tid = task_id or "default"

    try:
        if action == "get_logs":
            sup = _get_supervisor(tid)
            logs = []
            if sup is not None:
                snap = sup.snapshot()
                logs = [
                    {
                        "timestamp": e.ts,
                        "level": e.level,
                        "text": e.text,
                        "url": e.url,
                    }
                    for e in snap.console_errors
                ]
                if filter_level == "exception":
                    logs = [l for l in logs if l["level"] == "exception"]
                elif filter_level == "error":
                    logs = [l for l in logs if l["level"] == "error"]
                elif filter_level == "warning":
                    logs = [l for l in logs if l["level"] == "warning"]
            else:
                js = (
                    "(function() { "
                    "  if (window.__alexConsoleLog) { "
                    "    return JSON.stringify(window.__alexConsoleLog.slice(-100)); "
                    "  } "
                    "  return '[]'; "
                    "})()"
                )
                result = _supervisor_evaluate(js, task_id=task_id)
                if result.get("ok"):
                    raw = result.get("result", "[]")
                    if isinstance(raw, str):
                        try:
                            raw = json.loads(raw)
                        except Exception:
                            pass
                    if isinstance(raw, list):
                        logs = raw

            logs = logs[-max_entries:]
            levels_present = set(l.get("level", "log") for l in logs)
            return tool_result({
                "success": True,
                "action": "get_logs",
                "filter_level": filter_level,
                "count": len(logs),
                "levels_present": sorted(levels_present),
                "entries": logs,
            })

        elif action == "evaluate":
            if not expression:
                return tool_error("'expression' is required for evaluate")
            result = _supervisor_evaluate(
                expression,
                return_by_value=True,
                task_id=task_id,
                timeout=15.0,
            )
            if result.get("ok"):
                return tool_result({
                    "success": True,
                    "action": "evaluate",
                    "expression": expression[:200],
                    "result": result.get("result"),
                    "result_type": result.get("result_type"),
                })
            return tool_result({
                "success": False,
                "action": "evaluate",
                "expression": expression[:200],
                "error": result.get("error", "Unknown error"),
            })

        elif action == "clear":
            js = (
                "(function() { "
                "  console.clear(); "
                "  if (window.__alexConsoleLog) window.__alexConsoleLog = []; "
                "  return 'cleared'; "
                "})()"
            )
            _supervisor_evaluate(js, task_id=task_id)
            return tool_result({
                "success": True,
                "action": "clear",
                "message": "Console cleared.",
            })

        elif action == "monitor":
            if not monitor_event:
                return tool_error("'monitor_event' is required for monitor")

            if monitor_action == "start":
                js = (
                    f"(function() {{ "
                    f"  if (!window.__alexMonitors) window.__alexMonitors = {{}}; "
                    f"  if (window.__alexMonitors[{json.dumps(monitor_event)}]) return 'already_monitoring'; "
                    f"  const handler = (e) => {{ "
                    f"    console.log('ALEX_MONITOR:', {json.dumps(monitor_event)}, "
                    f"      e.target.tagName, e.target.className.substring(0, 50)); "
                    f"  }}; "
                    f"  window.__alexMonitors[{json.dumps(monitor_event)}] = handler; "
                    f"  document.addEventListener({json.dumps(monitor_event)}, handler, true); "
                    f"  return 'started'; "
                    f"}})()"
                )
                _supervisor_evaluate(js, task_id=task_id)
                _console_monitor_state[tid] = True
                return tool_result({
                    "success": True,
                    "action": "monitor",
                    "monitor_action": "start",
                    "event": monitor_event,
                    "message": f"Monitoring '{monitor_event}' events. Use browser_console_advanced action='get_logs' to see captured events.",
                })
            else:
                js = (
                    f"(function() {{ "
                    f"  if (window.__alexMonitors && window.__alexMonitors[{json.dumps(monitor_event)}]) {{ "
                    f"    document.removeEventListener({json.dumps(monitor_event)}, "
                    f"      window.__alexMonitors[{json.dumps(monitor_event)}], true); "
                    f"    delete window.__alexMonitors[{json.dumps(monitor_event)}]; "
                    f"    return 'stopped'; "
                    f"  }} "
                    f"  return 'not_monitoring'; "
                    f"}})()"
                )
                _supervisor_evaluate(js, task_id=task_id)
                _console_monitor_state.pop(tid, None)
                return tool_result({
                    "success": True,
                    "action": "monitor",
                    "monitor_action": "stop",
                    "event": monitor_event,
                })

        elif action == "get_exceptions":
            sup = _get_supervisor(tid)
            if sup is not None:
                snap = sup.snapshot()
                exceptions = [
                    {"timestamp": e.ts, "text": e.text, "url": e.url}
                    for e in snap.console_errors
                    if e.level in ("error", "exception")
                ]
            else:
                exceptions = []
            exceptions = exceptions[-max_entries:]
            return tool_result({
                "success": True,
                "action": "get_exceptions",
                "count": len(exceptions),
                "exceptions": exceptions,
            })

        else:
            return tool_error(f"Invalid action: {action}")
    except Exception as exc:
        logger.exception("browser_console_advanced failed")
        return tool_error(f"Console operation failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def _browser_devtools_check() -> bool:
    """Tools are available when CDP endpoint is reachable."""
    try:
        from tools.browser_tool import _get_cdp_override, check_browser_requirements
    except ImportError:
        return False
    if not check_browser_requirements():
        return False
    return bool(_get_cdp_override())


# ---------------------------------------------------------------------------
# Registry registrations
# ---------------------------------------------------------------------------

DEVTOOLS_TOOLSET = "browser-devtools"

registry.register(
    name="browser_inspect_element",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_INSPECT_ELEMENT_SCHEMA,
    handler=lambda args, **kw: browser_inspect_element(
        selector=args.get("selector", ""),
        pseudo=args.get("pseudo", ""),
        attributes=args.get("attributes", True),
        computed_styles=args.get("computed_styles", True),
        box_model=args.get("box_model", True),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="🔍",
)

registry.register(
    name="browser_edit_dom",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_EDIT_DOM_SCHEMA,
    handler=lambda args, **kw: browser_edit_dom(
        selector=args.get("selector", ""),
        action=args.get("action", ""),
        value=args.get("value", ""),
        attribute_name=args.get("attribute_name", ""),
        style_property=args.get("style_property", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="✏️",
)

registry.register(
    name="browser_inspect",
    toolset="browser",
    schema=BROWSER_INSPECT_ELEMENT_SCHEMA,
    handler=lambda args, **kw: browser_inspect_element(
        selector=args.get("selector", ""),
        pseudo=args.get("pseudo", ""),
        attributes=args.get("attributes", True),
        computed_styles=args.get("computed_styles", True),
        box_model=args.get("box_model", True),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="🔍",
)

registry.register(
    name="browser_edit_css",
    toolset="browser",
    schema=BROWSER_EDIT_DOM_SCHEMA,
    handler=lambda args, **kw: browser_edit_dom(
        selector=args.get("selector", ""),
        action=args.get("action", "set_style"),
        value=args.get("value", ""),
        style_property=args.get("style_property", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="🎨",
)

registry.register(
    name="browser_network",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_NETWORK_SCHEMA,
    handler=lambda args, **kw: browser_network(
        action=args.get("action", ""),
        filter_type=args.get("filter_type", "all"),
        max_entries=args.get("max_entries", 50),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="📡",
)

registry.register(
    name="browser_performance",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_PERFORMANCE_SCHEMA,
    handler=lambda args, **kw: browser_performance(
        action=args.get("action", ""),
        max_trace_entries=args.get("max_trace_entries", 200),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="⚡",
)

registry.register(
    name="browser_cookies",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_COOKIES_SCHEMA,
    handler=lambda args, **kw: browser_cookies(
        action=args.get("action", ""),
        name=args.get("name", ""),
        value=args.get("value", ""),
        domain=args.get("domain", ""),
        path=args.get("path", "/"),
        secure=args.get("secure", False),
        http_only=args.get("http_only", False),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="🍪",
)

registry.register(
    name="browser_storage",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_STORAGE_SCHEMA,
    handler=lambda args, **kw: browser_storage(
        storage_type=args.get("storage_type", ""),
        action=args.get("action", ""),
        key=args.get("key", ""),
        value=args.get("value", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="💾",
)

registry.register(
    name="browser_highlight",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_HIGHLIGHT_SCHEMA,
    handler=lambda args, **kw: browser_highlight(
        selector=args.get("selector", ""),
        action=args.get("action", ""),
        color=args.get("color", "red"),
        style=args.get("style", "outline"),
        duration=args.get("duration", 5),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="🔦",
)

registry.register(
    name="browser_screenshot_devtools",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_SCREENSHOT_SCHEMA,
    handler=lambda args, **kw: browser_screenshot(
        mode=args.get("mode", "viewport"),
        selector=args.get("selector", ""),
        format=args.get("format", "png"),
        quality=args.get("quality", 80),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="📷",
)

registry.register(
    name="browser_breakpoint",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_BREAKPOINT_SCHEMA,
    handler=lambda args, **kw: browser_breakpoint(
        action=args.get("action", ""),
        url=args.get("url", ""),
        line_number=args.get("line_number", 0),
        condition=args.get("condition", ""),
        event_name=args.get("event_name", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="⏸️",
)

registry.register(
    name="browser_accessibility",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_ACCESSIBILITY_SCHEMA,
    handler=lambda args, **kw: browser_accessibility(
        action=args.get("action", ""),
        selector=args.get("selector", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="♿",
)

registry.register(
    name="browser_coverage",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_COVERAGE_SCHEMA,
    handler=lambda args, **kw: browser_coverage(
        action=args.get("action", ""),
        reset_on_start=args.get("reset_on_start", True),
        max_entries=args.get("max_entries", 50),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="📊",
)

registry.register(
    name="browser_console_advanced",
    toolset=DEVTOOLS_TOOLSET,
    schema=BROWSER_CONSOLE_DEVTOOLS_SCHEMA,
    handler=lambda args, **kw: browser_console_advanced(
        action=args.get("action", ""),
        expression=args.get("expression", ""),
        filter_level=args.get("filter_level", "all"),
        max_entries=args.get("max_entries", 100),
        monitor_event=args.get("monitor_event", ""),
        monitor_action=args.get("monitor_action", "start"),
        task_id=kw.get("task_id"),
    ),
    check_fn=_browser_devtools_check,
    emoji="🖥️",
)
