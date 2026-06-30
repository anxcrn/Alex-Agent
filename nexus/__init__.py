"""Project Nexus — self-evolving engine for Alex Agent.

Nexus discovers, learns, builds, verifies, and merges new capabilities
(skills, tools, MCP servers, techniques) into the running Alex instance.
"""

__all__ = [
    "KnowledgeBase",
    "EvolutionPipeline",
    "NexusDaemon",
]


def __getattr__(name: str):
    """Lazy imports to avoid circular-import issues at module load time."""
    if name == "KnowledgeBase":
        from nexus.knowledge_base import KnowledgeBase
        return KnowledgeBase
    if name == "EvolutionPipeline":
        from nexus.pipeline import EvolutionPipeline
        return EvolutionPipeline
    if name == "NexusDaemon":
        from nexus.daemon import NexusDaemon
        return NexusDaemon
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
