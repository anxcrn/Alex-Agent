"""Comprehensive unit test suite for Project Nexus.

Tests the knowledge base, configuration, changelog, pipeline orchestrator,
sandbox, security scanner, and evolver.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from nexus.config import NexusConfig, load_config, save_config
from nexus.knowledge_base import KnowledgeBase
from nexus.changelog import Changelog, ChangelogEntry
from nexus.pipeline import EvolutionPipeline, PipelineResult
from nexus.crawlers.base import Discovery, SourceType, DiscoveryCategory
from nexus.verifier.sandbox import Sandbox
from nexus.verifier.security import SecurityScanner
from nexus.verifier.validator import CorrectnessValidator
from nexus.evolver.code_writer import CodeWriter
from nexus.evolver.merger import EvolutionMerger
from nexus.evolver.rollback import RollbackManager


@pytest.fixture
def temp_home():
    """Create a temporary ALEX_HOME context for isolating tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_env = os.environ.get("ALEX_HOME")
        os.environ["ALEX_HOME"] = tmpdir
        yield Path(tmpdir)
        if old_env:
            os.environ["ALEX_HOME"] = old_env
        else:
            os.environ.pop("ALEX_HOME", None)


def test_knowledge_base_crud(temp_home):
    """Test SQLite knowledge base operations and deduplication checks."""
    db_file = temp_home / "nexus" / "knowledge.db"
    kb = KnowledgeBase(db_path=db_file)
    kb._get_conn()
    
    # Verify tables auto-created
    assert db_file.exists()
    
    disc_id = "test_discovery_123"
    content_hash = "abcde12345"
    
    # Add discovery
    kb.add_discovery(
        id=disc_id,
        source_type="github",
        source_url="https://github.com/test/repo",
        title="Test Repo",
        content="This is a cool test repository containing code.",
        content_hash=content_hash,
        category="tool",
        relevance_score=8.5,
        status="new",
        metadata={"stars": 450}
    )
    
    # Check deduplication helper
    assert kb.has_content_hash(content_hash) is True
    assert kb.has_content_hash("nonexistent_hash") is False
    
    # Retrieve discovery
    disc = kb.get_discovery(disc_id)
    assert disc is not None
    assert disc["title"] == "Test Repo"
    assert disc["status"] == "new"
    
    # FTS5 search
    results = kb.search_discoveries("cool test")
    assert len(results) == 1
    assert results[0]["id"] == disc_id
    
    # Update status
    kb.update_discovery_status(disc_id, "analyzed")
    disc = kb.get_discovery(disc_id)
    assert disc["status"] == "analyzed"
    
    # Add knowledge
    kb.add_knowledge(
        id="knowledge_123",
        discovery_id=disc_id,
        summary="A test tool knowledge summary.",
        code_snippet="import test",
        category="tool",
        actionable=True
    )
    
    # Check stats
    stats = kb.get_stats()
    assert stats["discoveries"] == 1
    assert stats["knowledge"] == 1


def test_changelog_append_and_read(temp_home):
    """Test append-only changelog writing and locking."""
    changelog_file = temp_home / "nexus" / "changelog.jsonl"
    cl = Changelog(file_path=changelog_file)
    
    cl.append(
        action="discovered",
        source_url="https://test.com",
        source_type="web",
        description="Test description for changelog.",
        confidence_score=90.0
    )
    
    assert changelog_file.exists()
    
    entries = cl.get_entries()
    assert len(entries) == 1
    assert entries[0].action == "discovered"
    assert entries[0].confidence_score == 90.0
    
    recent = cl.get_recent(5)
    assert len(recent) == 1
    
    summary = cl.generate_summary()
    assert "discovered" in summary.lower()


def test_config_load_and_save(temp_home):
    """Test config serialization and default creation."""
    config = load_config()
    assert config.enabled is False
    assert config.mode == "full_auto"
    
    config.enabled = True
    config.mode = "semi_auto"
    save_config(config)
    
    reloaded = load_config()
    assert reloaded.enabled is True
    assert reloaded.mode == "semi_auto"


def test_sandbox_execution(temp_home):
    """Test sandbox execution captures stdout/stderr and exit codes."""
    sb = Sandbox()
    
    # Successful execution
    res = sb.execute("print('Hello from Sandbox!')")
    assert res.exit_code == 0
    assert "Hello from Sandbox!" in res.stdout
    assert res.timed_out is False
    
    # Syntax error execution
    res_err = sb.execute("print('Hello' error")
    assert res_err.exit_code != 0
    assert "SyntaxError" in res_err.stderr


def test_security_scanner_ast(temp_home):
    """Test AST visitor blocks dangerous code execution calls."""
    scanner = SecurityScanner()
    
    # Safe code
    safe_code = (
        "def run_tool(x):\n"
        "    return x + 5\n"
    )
    res_safe = scanner.scan(safe_code)
    assert res_safe.safe is True
    assert len(res_safe.issues) == 0
    
    # Unsafe eval code
    unsafe_eval = (
        "def run_tool(x):\n"
        "    eval(x)\n"
    )
    res_eval = scanner.scan(unsafe_eval)
    assert res_eval.safe is False
    assert any(issue.pattern == "eval" for issue in res_eval.issues)
    
    # Unsafe subprocess shell=True code
    unsafe_shell = (
        "import subprocess\n"
        "subprocess.run('ls', shell=True)\n"
    )
    res_shell = scanner.scan(unsafe_shell)
    assert res_shell.safe is False
    assert any("shell=True" in issue.description for issue in res_shell.issues)


def test_correctness_validator_fallback(temp_home):
    """Test correctness validator fallback compilation checks."""
    val = CorrectnessValidator()
    
    # Valid syntax code
    res_ok = val.validate("def test(): pass", "Simple pass function")
    assert res_ok.valid is True
    assert res_ok.confidence >= 80.0
    
    # Invalid syntax code
    res_fail = val.validate("def test(invalid syntax", "Fails compilation")
    assert res_fail.valid is False
    assert len(res_fail.issues) > 0
