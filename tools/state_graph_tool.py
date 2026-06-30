import os
import json
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional
from tools.registry import registry
from tools.delegate_tool import _build_child_agent, _normalize_role

logger = logging.getLogger("hermes.state_graph")

def _parse_subagent_json_output(output: str) -> dict:
    """Attempts to extract and parse a JSON block from the subagent's response."""
    try:
        # Check for ```json ... ``` code blocks
        if "```json" in output:
            parts = output.split("```json")
            json_str = parts[1].split("```")[0].strip()
            return json.loads(json_str)
        elif "```" in output:
            parts = output.split("```")
            json_str = parts[1].split("```")[0].strip()
            return json.loads(json_str)
        # Fallback to direct parse
        return json.loads(output.strip())
    except Exception:
        return {}

def run_agent_graph(graph: dict, initial_state: dict, parent_agent: Any = None) -> str:
    """Execute a multi-agent workflow defined as a state-graph."""
    if not parent_agent:
        return json.dumps({"success": False, "error": "State-graph requires a parent agent context."})
        
    state = dict(initial_state)
    nodes = graph.get("nodes", {})
    edges = graph.get("edges", {})
    cond_edges = graph.get("conditional_edges", {})
    
    current_node = graph.get("start_node")
    if not current_node and nodes:
        current_node = list(nodes.keys())[0]
        
    history = []
    max_steps = 15
    steps = 0
    
    while current_node and current_node.lower() != "end" and steps < max_steps:
        steps += 1
        if current_node not in nodes:
            history.append(f"Transitioned to unknown node: {current_node}. Terminating.")
            break
            
        node_def = nodes[current_node]
        prompt_tmpl = node_def.get("prompt", "")
        
        # Safely format template variables
        try:
            formatted_prompt = prompt_tmpl.format(**state)
        except KeyError as ke:
            # Fallback if variable is missing in state
            state[str(ke).strip("'")] = ""
            formatted_prompt = prompt_tmpl.format(**state)
            
        role = _normalize_role(node_def.get("role", "leaf"))
        toolsets = node_def.get("toolsets")
        model = node_def.get("model")
        
        history.append(f"Step {steps}: Running node '{current_node}' with role '{role}'")
        
        child_task_id = f"graph-{current_node}-{uuid.uuid4().hex[:8]}"
        
        try:
            # Build the child agent using the core delegation builder
            child = _build_child_agent(
                task_index=steps,
                goal=formatted_prompt,
                context=node_def.get("context"),
                toolsets=toolsets,
                model=model,
                max_iterations=node_def.get("max_iterations", 10),
                task_count=1,
                parent_agent=parent_agent,
                role=role
            )
            
            # Execute the conversation
            output = child.run_conversation(
                user_message=formatted_prompt,
                task_id=child_task_id
            )
            
            # Store raw output
            state[current_node] = output
            
            # Attempt to parse updates to state
            updates = _parse_subagent_json_output(output)
            if isinstance(updates, dict) and updates:
                state.update(updates)
                history.append(f"Node '{current_node}' output parsed successfully as JSON state updates.")
            
        except Exception as e:
            history.append(f"Node '{current_node}' failed with exception: {e}")
            break
            
        # Determine next transition
        next_node = None
        if current_node in edges:
            next_node = edges[current_node]
        elif current_node in cond_edges:
            cond_def = cond_edges[current_node]
            state_key = cond_def.get("state_key")
            val = str(state.get(state_key, "")).strip().lower()
            mapping = cond_def.get("mapping", {})
            next_node = mapping.get(val)
            if not next_node:
                next_node = mapping.get("default")
                
        if not next_node:
            history.append(f"No transition defined from node '{current_node}'. Terminating.")
            break
            
        current_node = next_node
        
    return json.dumps({
        "success": True,
        "history": history,
        "final_state": state
    }, ensure_ascii=False)


registry.register(
    name="run_agent_graph",
    toolset="delegation",
    schema={
        "name": "run_agent_graph",
        "description": "Execute a multi-agent workflow defined as a state-graph. Transitions between specialized worker nodes based on state variables and outputs.",
        "parameters": {
            "type": "object",
            "properties": {
                "graph": {
                    "type": "object",
                    "description": "The graph structure containing 'nodes' definitions, static 'edges', and 'conditional_edges'.",
                    "properties": {
                        "start_node": {"type": "string", "description": "The initial node to execute"},
                        "nodes": {
                            "type": "object",
                            "description": "Mapping of node names to their prompt template, role, and configuration."
                        },
                        "edges": {
                            "type": "object",
                            "description": "Static transitions from node to node: {'node_a': 'node_b'}"
                        },
                        "conditional_edges": {
                            "type": "object",
                            "description": "Transitions based on state variables: {'node_a': {'state_key': 'decision', 'mapping': {'yes': 'node_b', 'no': 'node_c'}}}"
                        }
                    },
                    "required": ["nodes"]
                },
                "initial_state": {
                    "type": "object",
                    "description": "Initial state variables for the graph execution."
                }
            },
            "required": ["graph", "initial_state"]
        }
    },
    handler=lambda args, **kw: run_agent_graph(
        graph=args.get("graph", {}),
        initial_state=args.get("initial_state", {}),
        parent_agent=kw.get("parent_agent")
    ),
    emoji="🕸️"
)
