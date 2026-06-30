"""Hacker News crawler for discovering trending AI frameworks, tools, and discussions.

Queries the Hacker News Algolia Search API for keyword matches.
"""

import logging
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class HackerNewsCrawler(BaseCrawler):
    """Crawler for discovering newly launched tools and papers on Hacker News."""

    def __init__(self, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)

    @property
    def name(self) -> str:
        return "hackernews"

    @property
    def source_type(self) -> SourceType:
        return SourceType.HACKERNEWS

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        queries = ["mcp server", "ai agent tool", "open source agent"]
        scanned = 0
        
        for q in queries:
            if scanned >= self._max_pages:
                break
                
            url = f"https://hn.algolia.com/api/v1/search?query={q}&tags=story"
            data = self._http_get(url)
            scanned += 1
            
            if not data or "hits" not in data:
                continue
                
            for hit in data["hits"]:
                title = hit.get("title", "")
                story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                points = hit.get("points", 0)
                
                if points < 10:
                    continue
                    
                content = (
                    f"Hacker News Story: {title}\n"
                    f"Author: {hit.get('author')}\n"
                    f"Points: {points}\n"
                    f"Comments: {hit.get('num_comments')}\n"
                    f"URL: {story_url}\n"
                )
                
                disc = self._make_discovery(
                    source_url=story_url,
                    title=f"Hacker News Story: {title}",
                    content=content,
                    category=DiscoveryCategory.TECHNIQUE,
                    relevance_score=6.5 + min(3.5, points / 100.0),
                    metadata={
                        "hn_id": hit.get("objectID"),
                        "points": points,
                        "comments": hit.get("num_comments")
                    }
                )
                result.discoveries.append(disc)
                
        result.pages_scanned = scanned
        return result
