from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class ConversationMessage:
    role: str  # "user", "assistant", "tool"
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str | None = None


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class AgentConfig:
    model: str = ""
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    api_mode: str = ""
    max_iterations: int = 90
    enabled_toolsets: list[str] | None = None
    disabled_toolsets: list[str] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning_effort: str = ""
    system_prompt: str = ""
    working_directory: str = ""
    environment: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentResult:
    success: bool
    content: str
    status: AgentStatus
    session_id: str | None = None
    iterations_used: int = 0
    total_cost_usd: float = 0.0
    error: str | None = None
    messages: list[ConversationMessage] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
