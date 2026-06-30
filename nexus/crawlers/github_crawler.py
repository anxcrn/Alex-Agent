"""GitHub crawler for discovering new tools, agent frameworks, and MCP servers.

Scans the GitHub Search API for trending or recently updated repositories matching
AI agent topics or MCP tags.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class GitHubCrawler(BaseCrawler):
    """Crawler for discovering open-source AI assets on GitHub."""

    def __init__(self, stars_threshold: int = 100, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)
        self.stars_threshold = stars_threshold

    @property
    def name(self) -> str:
        return "github"

    @property
    def source_type(self) -> SourceType:
        return SourceType.GITHUB

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        # Prepare authorization headers if GITHUB_TOKEN is available
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "NexusCrawler/1.0"
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
            
        queries = [
            "topic:mcp-server",
            "topic:ai-agent",
            "topic:llm-tools",
            "mcp-server language:python",
            "model-context-protocol"
        ]
        
        scanned = 0
        for query in queries:
            if scanned >= self._max_pages:
                break
                
            url = "https://api.github.com/search/repositories"
            params = {
                "q": f"{query} stars:>={self.stars_threshold}",
                "sort": "stars",
                "order": "desc",
                "per_page": "10"
            }
            
            logger.debug("[Nexus/GitHub] Querying API: %s with params %s", url, params)
            data = self._http_get(url, headers=headers, params=params)
            scanned += 1
            
            if not data or "items" not in data:
                continue
                
            for item in data["items"]:
                repo_url = item.get("html_url", "")
                description = item.get("description") or ""
                stars = item.get("stargazers_count", 0)
                topics = item.get("topics", [])
                
                # Determine category
                category = DiscoveryCategory.TOOL
                if "mcp-server" in topics or "mcp" in repo_url.lower():
                    category = DiscoveryCategory.MCP_SERVER
                elif "agent-framework" in topics or "framework" in repo_url.lower():
                    category = DiscoveryCategory.FRAMEWORK
                elif "library" in repo_url.lower():
                    category = DiscoveryCategory.LIBRARY
                    
                content = (
                    f"Repository: {item.get('full_name')}\n"
                    f"Description: {description}\n"
                    f"Primary Language: {item.get('language')}\n"
                    f"Stars: {stars}\n"
                    f"Forks: {item.get('forks_count')}\n"
                    f"Topics: {', '.join(topics)}\n"
                )
                
                # Relevance score calculation
                relevance = min(10.0, 5.0 + (stars / 1000.0))
                
                disc = self._make_discovery(
                    source_url=repo_url,
                    title=f"GitHub Repository: {item.get('full_name')}",
                    content=content,
                    category=category,
                    relevance_score=relevance,
                    metadata={
                        "name": item.get("name"),
                        "owner": item.get("owner", {}).get("login"),
                        "stars": stars,
                        "language": item.get("language"),
                        "topics": topics
                    }
                )
                result.discoveries.append(disc)
                
        result.pages_scanned = scanned
        return result
