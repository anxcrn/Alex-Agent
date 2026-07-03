from __future__ import annotations


class AlexSDKError(Exception):
    """Base exception for all SDK errors."""


class AgentTimeoutError(AlexSDKError):
    """Raised when an agent execution exceeds the timeout."""


class AgentNotFoundError(AlexSDKError):
    """Raised when the requested agent or session is not found."""


class AgentExecutionError(AlexSDKError):
    """Raised when an agent execution fails."""


class AgentUnauthorizedError(AlexSDKError):
    """Raised when authentication fails."""
