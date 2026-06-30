"""Evolution pipeline orchestrator for Project Nexus.

Runs the 6-step pipeline:
1. Discover: Execute enabled crawlers to find new items.
2. Deduplicate: Filter out discoveries already processed.
3. Analyze: Understand content, score relevance, extract knowledge.
4. Build: Generate SKILL.md, tools, or MCP configurations.
5. Verify: Test code in sandbox, scan security AST, validate correctness.
6. Merge: Write verified updates to source tree and trigger reload.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import Discovery, CrawlResult
from nexus.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Aggregated statistics for a single pipeline run."""
    discovered: int = 0
    deduplicated: int = 0
    analyzed: int = 0
    built: int = 0
    verified: int = 0
    merged: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class EvolutionPipeline:
    """Orchestrates the entire discover-to-merge flow for self-evolution."""

    def __init__(self, kb: Optional[KnowledgeBase] = None, changelog: Any = None) -> None:
        """Initialize the pipeline.

        Args:
            kb: Existing KnowledgeBase instance.
            changelog: Existing Changelog instance.
        """
        from nexus.knowledge_base import KnowledgeBase
        from nexus.changelog import Changelog
        
        self.kb = kb or KnowledgeBase()
        self.changelog = changelog or Changelog()

    def discover(self) -> List[Discovery]:
        """Step 1: Execute all enabled crawlers and collect discoveries."""
        from nexus.config import load_config
        from nexus.crawlers.github_crawler import GitHubCrawler
        from nexus.crawlers.mcp_registry import MCPRegistryCrawler
        from nexus.crawlers.pypi_crawler import PyPICrawler
        from nexus.crawlers.npm_crawler import NPMCrawler
        from nexus.crawlers.reddit_crawler import RedditCrawler
        from nexus.crawlers.hackernews_crawler import HackerNewsCrawler
        from nexus.crawlers.youtube_crawler import YouTubeCrawler
        from nexus.crawlers.arxiv_crawler import ArXivCrawler
        from nexus.crawlers.web_crawler import WebCrawler
        from nexus.crawlers.docs_crawler import DocsCrawler

        config = load_config()
        if not config.enabled:
            logger.info("[Nexus/Pipeline] Nexus is disabled; skipping discovery")
            return []

        crawlers = []
        if config.sources.github:
            crawlers.append(GitHubCrawler(config.crawlers.github_stars_threshold, config.crawlers.max_pages_per_scan))
        if config.sources.mcp_registries:
            crawlers.append(MCPRegistryCrawler(config.crawlers.max_pages_per_scan))
        if config.sources.pypi:
            crawlers.append(PyPICrawler(config.crawlers.max_pages_per_scan))
        if config.sources.npm:
            crawlers.append(NPMCrawler(config.crawlers.max_pages_per_scan))
        if config.sources.reddit:
            crawlers.append(RedditCrawler(config.crawlers.max_pages_per_scan))
        if config.sources.hackernews:
            crawlers.append(HackerNewsCrawler(config.crawlers.max_pages_per_scan))
        if config.sources.youtube:
            crawlers.append(YouTubeCrawler(config.crawlers.max_pages_per_scan, config.crawlers.youtube_channels))
        if config.sources.arxiv:
            crawlers.append(ArXivCrawler(config.crawlers.max_pages_per_scan))
        if config.sources.web:
            crawlers.append(WebCrawler(config.crawlers.max_pages_per_scan))
        if config.sources.docs:
            crawlers.append(DocsCrawler(config.crawlers.max_pages_per_scan))

        discoveries: List[Discovery] = []
        for crawler in crawlers:
            logger.info("[Nexus/Pipeline] Running crawler: %s", crawler.name)
            result: CrawlResult = crawler.safe_crawl()
            for disc in result.discoveries:
                discoveries.append(disc)
            if result.errors:
                logger.warning("[Nexus/Pipeline] Crawler %s reported errors: %s", crawler.name, result.errors)

        return discoveries

    def deduplicate(self, discoveries: List[Discovery]) -> List[Discovery]:
        """Step 2: Filter out discoveries already present in the knowledge base."""
        new_discoveries: List[Discovery] = []
        for disc in discoveries:
            if self.kb.has_content_hash(disc.content_hash):
                logger.debug("[Nexus/Pipeline] Discovery already known (content hash exists): %s", disc.title)
                continue
            new_discoveries.append(disc)
        return new_discoveries

    def run_cycle(self) -> PipelineResult:
        """Execute one complete discovery-to-merge pipeline run cycle."""
        result = PipelineResult()
        
        try:
            # 1. Discover
            logger.info("[Nexus/Pipeline] Starting discovery phase...")
            raw_discoveries = self.discover()
            result.discovered = len(raw_discoveries)
            logger.info("[Nexus/Pipeline] Discovered %d total items", result.discovered)

            # 2. Deduplicate
            logger.info("[Nexus/Pipeline] Starting deduplication phase...")
            new_discoveries = self.deduplicate(raw_discoveries)
            result.deduplicated = result.discovered - len(new_discoveries)
            logger.info("[Nexus/Pipeline] Deduplicated %d items. %d new items to process", 
                        result.deduplicated, len(new_discoveries))

            # Store new discoveries in KB
            for disc in new_discoveries:
                self.kb.add_discovery(
                    id=disc.content_hash[:16],
                    source_type=disc.source_type.value,
                    source_url=disc.source_url,
                    title=disc.title,
                    content=disc.content,
                    content_hash=disc.content_hash,
                    category=disc.category.value,
                    relevance_score=disc.relevance_score,
                    status="new",
                    metadata=disc.metadata
                )

            # Import learner, verifier, evolver modules dynamically to avoid circular dependencies
            from nexus.learner.analyzer import KnowledgeAnalyzer
            from nexus.learner.skill_builder import SkillBuilder
            from nexus.learner.tool_builder import ToolBuilder
            from nexus.learner.mcp_integrator import MCPIntegrator

            from nexus.verifier.tester import EvolutionTester
            from nexus.verifier.security import SecurityScanner
            from nexus.verifier.validator import CorrectnessValidator

            from nexus.evolver.merger import EvolutionMerger

            analyzer = KnowledgeAnalyzer()
            skill_builder = SkillBuilder()
            tool_builder = ToolBuilder()
            mcp_integrator = MCPIntegrator()

            tester = EvolutionTester()
            security_scanner = SecurityScanner()
            validator = CorrectnessValidator()

            merger = EvolutionMerger()

            # Process each new discovery
            for disc in new_discoveries:
                disc_id = disc.content_hash[:16]
                try:
                    # 3. Analyze
                    logger.info("[Nexus/Pipeline] Analyzing: %s", disc.title)
                    analysis = analyzer.analyze(disc)
                    if analysis.relevance_to_hermes < 5.0 or not analysis.actionable:
                        logger.info("[Nexus/Pipeline] Discovery skipped (relevance too low or not actionable): %s", disc.title)
                        self.kb.update_discovery_status(disc_id, "rejected")
                        continue
                    
                    self.kb.add_knowledge(
                        discovery_id=disc_id,
                        summary=analysis.what_does_it_do,
                        code_snippet=analysis.how_to_use,
                        category=analysis.what_is_it,
                        actionable=analysis.actionable,
                        metadata={"actionable_items": analysis.actionable_items}
                    )
                    self.kb.update_discovery_status(disc_id, "analyzed")
                    result.analyzed += 1

                    # Log to changelog
                    self.changelog.append(
                        action="analyzed",
                        source_url=disc.source_url,
                        source_type=disc.source_type.value,
                        description=f"Analyzed {disc.title}: {analysis.what_does_it_do}",
                        confidence_score=analysis.relevance_to_hermes * 10
                    )

                    # 4. Build
                    logger.info("[Nexus/Pipeline] Building: %s (Type: %s)", disc.title, analysis.what_is_it)
                    build_success = False
                    build_error = None
                    staging_path = ""
                    entity_name = ""

                    if analysis.what_is_it == "skill":
                        build_res = skill_builder.build(analysis, disc)
                        build_success = build_res.success
                        build_error = build_res.error
                        staging_path = build_res.skill_path
                        entity_name = build_res.skill_name
                    elif analysis.what_is_it == "tool":
                        build_res = tool_builder.build(analysis, disc)
                        build_success = build_res.success
                        build_error = build_res.error
                        staging_path = build_res.file_path
                        entity_name = build_res.tool_name
                    elif analysis.what_is_it == "mcp_server":
                        build_res = mcp_integrator.integrate(disc)
                        build_success = build_res.success
                        build_error = build_res.error
                        staging_path = f"mcps/{build_res.server_name}"
                        entity_name = build_res.server_name
                    else:
                        logger.info("[Nexus/Pipeline] Non-buildable category: %s", analysis.what_is_it)
                        self.kb.update_discovery_status(disc_id, "completed")
                        continue

                    if not build_success:
                        logger.warning("[Nexus/Pipeline] Build failed for %s: %s", disc.title, build_error)
                        self.kb.update_discovery_status(disc_id, "failed_build")
                        result.failed += 1
                        continue

                    self.kb.update_discovery_status(disc_id, "built")
                    result.built += 1

                    # 5. Verify
                    logger.info("[Nexus/Pipeline] Verifying generated entity: %s", entity_name)
                    verify_passed = False
                    verification_details = ""
                    
                    # AST Security Scan
                    if analysis.what_is_it == "tool":
                        security_res = security_scanner.scan_file(staging_path)
                    else:
                        security_res = security_scanner.scan_text(analysis.how_to_use)

                    if not security_res.safe:
                        logger.warning("[Nexus/Pipeline] Security block for %s: %s", entity_name, security_res.issues)
                        self.kb.update_discovery_status(disc_id, "failed_security")
                        result.failed += 1
                        continue

                    # Functional Sandbox Testing
                    if analysis.what_is_it == "skill":
                        test_res = tester.test_skill(staging_path)
                    elif analysis.what_is_it == "tool":
                        test_res = tester.test_tool(staging_path)
                    elif analysis.what_is_it == "mcp_server":
                        test_res = tester.test_mcp(build_res.config_entry)

                    if not test_res.passed:
                        logger.warning("[Nexus/Pipeline] Testing failed for %s: %s", entity_name, test_res.errors)
                        self.kb.update_discovery_status(disc_id, "failed_testing")
                        result.failed += 1
                        continue

                    # LLM Correctness Validation
                    if analysis.what_is_it == "tool":
                        with open(staging_path, 'r', encoding='utf-8') as f:
                            code_to_val = f.read()
                        val_res = validator.validate(code_to_val, analysis.what_does_it_do)
                        verify_passed = val_res.valid and val_res.confidence >= 80.0
                        verification_details = f"Confidence: {val_res.confidence}. Issues: {val_res.issues}"
                    else:
                        verify_passed = True
                        verification_details = "Auto-passed non-code asset validation"

                    if not verify_passed:
                        logger.warning("[Nexus/Pipeline] Validation failed for %s: %s", entity_name, verification_details)
                        self.kb.update_discovery_status(disc_id, "failed_validation")
                        result.failed += 1
                        continue

                    self.kb.update_discovery_status(disc_id, "verified")
                    result.verified += 1

                    # Log to changelog
                    self.changelog.append(
                        action="verified",
                        source_url=disc.source_url,
                        source_type=disc.source_type.value,
                        description=f"Verified build of {entity_name}: {verification_details}",
                        confidence_score=95.0
                    )

                    # 6. Merge
                    logger.info("[Nexus/Pipeline] Merging entity to codebase: %s", entity_name)
                    if analysis.what_is_it == "skill":
                        merge_res = merger.merge_skill(entity_name, staging_path)
                    elif analysis.what_is_it == "tool":
                        merge_res = merger.merge_tool(entity_name, staging_path)
                    elif analysis.what_is_it == "mcp_server":
                        merge_res = merger.merge_mcp(entity_name, build_res.config_entry)

                    if not merge_res.success:
                        logger.error("[Nexus/Pipeline] Merge failed for %s: %s", entity_name, merge_res.error)
                        self.kb.update_discovery_status(disc_id, "failed_merge")
                        result.failed += 1
                        continue

                    self.kb.update_discovery_status(disc_id, "merged")
                    result.merged += 1

                    # Add to FTS log
                    self.kb.add_evolution(
                        id=uuid_str(),
                        changelog_id=merge_res.rollback_token,
                        file_path=merge_res.merged_files[0] if merge_res.merged_files else "",
                        action="create",
                        backup_path="",
                        diff="",
                        verified=True
                    )

                    # Final merge log to changelog
                    self.changelog.append(
                        action="merged",
                        source_url=disc.source_url,
                        source_type=disc.source_type.value,
                        description=f"Successfully merged {entity_name} into codebase",
                        file_path=merge_res.merged_files[0] if merge_res.merged_files else "",
                        rollback_token=merge_res.rollback_token,
                        confidence_score=100.0
                    )

                except Exception as e:
                    logger.error("[Nexus/Pipeline] Error processing discovery %s: %s", disc.title, e, exc_info=True)
                    self.kb.update_discovery_status(disc_id, "error")
                    result.failed += 1
                    result.errors.append(f"Error processing {disc.title}: {e}")

        except Exception as e:
            logger.error("[Nexus/Pipeline] Pipeline execution halted: %s", e, exc_info=True)
            result.errors.append(f"Pipeline halted: {e}")

        return result


def uuid_str() -> str:
    """Helper to generate a random UUID string."""
    import uuid
    return str(uuid.uuid4())
