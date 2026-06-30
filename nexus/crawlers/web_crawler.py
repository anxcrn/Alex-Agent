"""Web search crawler for discovering newly launched tools, API changes, and blog posts.

Uses DuckDuckGo Instant Answer API as a light search wrapper.
"""

import logging
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class WebCrawler(BaseCrawler):
    """Crawler for discovering newly launched tools and API updates across the general web."""

    def __init__(self, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)

    @property
    def name(self) -> str:
        return "web"

    @property
    def source_type(self) -> SourceType:
        return SourceType.WEB

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        queries = ["new mcp server", "ai coding agent tool framework"]
        scanned = 0
        
        for q in queries:
            if scanned >= self._max_pages:
                break
                
            # DuckDuckGo light API
            url = "https://api.duckduckgo.com/"
            params = {
                "q": q,
                "format": "json",
                "no_html": "1"
            }
            data = self._http_get(url, params=params)
            scanned += 1
            
            if not data:
                continue
                
            # Parse topics or results
            topics = data.get("RelatedTopics", [])
            for topic in topics:
                if "Text" in topic and "FirstURL" in topic:
                    text = topic["Text"]
                    first_url = topic["FirstURL"]
                    
                    disc = self._make_discovery(
                        source_url=first_url,
                        title=f"Web search ({q}): {text[:50]}...",
                        content=f"Source: {first_url}\nText: {text}\n",
                        category=DiscoveryCategory.TOOL,
                        relevance_score=5.5,
                        metadata={"url": first_url, "query": q}
                    )
                    result.discoveries.append(disc)
                    
        result.pages_scanned = scanned
        return result
