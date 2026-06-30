"""Docs crawler for monitoring API updates and official documentation changes.

Scrapes target docs and checks for content hash updates to flag new releases.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home
from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class DocsCrawler(BaseCrawler):
    """Crawler for monitoring changes to official documentation sites."""

    def __init__(self, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)
        self._hash_store_path = get_hermes_home() / "nexus" / "docs_hashes.json"

    @property
    def name(self) -> str:
        return "docs"

    @property
    def source_type(self) -> SourceType:
        return SourceType.DOCS

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        target_urls = [
            "https://spec.modelcontextprotocol.io/specification/",
            "https://docs.anthropic.com/en/docs/about-claude/models",
            "https://platform.openai.com/docs/changelog"
        ]
        
        # Load previous hashes
        old_hashes: Dict[str, str] = {}
        if self._hash_store_path.exists():
            try:
                old_hashes = json.loads(self._hash_store_path.read_text())
            except Exception:
                pass
                
        new_hashes = dict(old_hashes)
        scanned = 0
        
        for url in target_urls:
            if scanned >= self._max_pages:
                break
                
            html_text = self._http_get_text(url)
            scanned += 1
            if not html_text:
                continue
                
            from nexus.crawlers.base import Discovery
            # Create a temporary discovery to get content hash
            temp_disc = Discovery(
                source_type=self.source_type,
                source_url=url,
                title=f"Doc change: {url}",
                content=html_text[:5000]
            )
            
            h = temp_disc.content_hash
            prev_hash = old_hashes.get(url)
            
            if prev_hash != h:
                # Document has changed!
                new_hashes[url] = h
                
                disc = self._make_discovery(
                    source_url=url,
                    title=f"Documentation Update: {url}",
                    content=f"Official documentation at {url} has been updated since the last crawl.\nContent preview:\n{html_text[:3000]}",
                    category=DiscoveryCategory.API,
                    relevance_score=7.8,
                    metadata={"url": url, "previous_hash": prev_hash, "new_hash": h}
                )
                result.discoveries.append(disc)
                
        # Save updated hashes
        try:
            self._hash_store_path.parent.mkdir(parents=True, exist_ok=True)
            self._hash_store_path.write_text(json.dumps(new_hashes, indent=2))
        except Exception as e:
            logger.warning("[Nexus/Docs] Failed to write docs_hashes.json: %s", e)
            
        result.pages_scanned = scanned
        return result
