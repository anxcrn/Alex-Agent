"""PyPI package registry crawler for discovering new Python-based tools and MCPs.

Monitors PyPI updates and searches for keywords like 'mcp', 'agent', and 'tool'.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class PyPICrawler(BaseCrawler):
    """Crawler for discovering new Python libraries on PyPI."""

    def __init__(self, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)

    @property
    def name(self) -> str:
        return "pypi"

    @property
    def source_type(self) -> SourceType:
        return SourceType.PYPI

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        # Scrape PyPI recent updates RSS
        url = "https://pypi.org/rss/updates.xml"
        rss_text = self._http_get_text(url)
        
        if not rss_text:
            return result
            
        try:
            root = ET.fromstring(rss_text)
            scanned = 0
            
            for item in root.findall(".//item"):
                if scanned >= self._max_pages:
                    break
                    
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                description = item.find("description").text if item.find("description") is not None else ""
                
                # Check for interesting keywords
                keywords = ["mcp", "agent", "llm-tool", "modelcontextprotocol"]
                match = any(kw in title.lower() or kw in description.lower() for kw in keywords)
                
                if match:
                    # Determine category
                    category = DiscoveryCategory.LIBRARY
                    if "mcp" in title.lower():
                        category = DiscoveryCategory.MCP_SERVER
                    elif "agent" in title.lower():
                        category = DiscoveryCategory.TOOL
                        
                    content = (
                        f"PyPI Package: {title}\n"
                        f"Description: {description}\n"
                        f"URL: {link}\n"
                    )
                    
                    disc = self._make_discovery(
                        source_url=link,
                        title=f"PyPI Package: {title}",
                        content=content,
                        category=category,
                        relevance_score=6.5,
                        metadata={"name": title, "url": link}
                    )
                    result.discoveries.append(disc)
                    
                scanned += 1
            result.pages_scanned = 1  # RSS feed counts as 1 main request
        except Exception as e:
            result.errors.append(f"PyPI RSS parse error: {e}")
            
        return result
