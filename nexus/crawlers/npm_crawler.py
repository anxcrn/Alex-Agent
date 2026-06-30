"""npm package registry crawler for discovering new Node-based tools and MCPs.

Searches the npm registry for keywords like 'mcp-server', 'model-context-protocol', and 'ai-agent'.
"""

import logging
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class NPMCrawler(BaseCrawler):
    """Crawler for discovering new Node.js libraries and tools on npm."""

    def __init__(self, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)

    @property
    def name(self) -> str:
        return "npm"

    @property
    def source_type(self) -> SourceType:
        return SourceType.NPM

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        search_terms = ["mcp-server", "model-context-protocol", "ai-agent-tool"]
        scanned = 0
        
        for term in search_terms:
            if scanned >= self._max_pages:
                break
                
            url = f"https://registry.npmjs.org/-/v1/search?text={term}&size=20"
            data = self._http_get(url)
            scanned += 1
            
            if not data or "objects" not in data:
                continue
                
            for obj in data["objects"]:
                package = obj.get("package", {})
                name = package.get("name", "")
                description = package.get("description", "")
                npm_url = package.get("links", {}).get("npm", "")
                
                category = DiscoveryCategory.LIBRARY
                if "mcp" in name.lower():
                    category = DiscoveryCategory.MCP_SERVER
                elif "agent" in name.lower() or "tool" in name.lower():
                    category = DiscoveryCategory.TOOL
                    
                content = (
                    f"npm Package: {name}\n"
                    f"Description: {description}\n"
                    f"Version: {package.get('version')}\n"
                    f"Publisher: {package.get('publisher', {}).get('username')}\n"
                    f"URL: {npm_url}\n"
                )
                
                disc = self._make_discovery(
                    source_url=npm_url,
                    title=f"npm Package: {name}",
                    content=content,
                    category=category,
                    relevance_score=6.8,
                    metadata={"name": name, "url": npm_url}
                )
                result.discoveries.append(disc)
                
        result.pages_scanned = scanned
        return result
