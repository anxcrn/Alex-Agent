"""ArXiv crawler for discovering new AI papers, techniques, and benchmarks.

Queries the ArXiv API for papers matching 'cs.AI' and 'agent'.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class ArXivCrawler(BaseCrawler):
    """Crawler for discovering newly published scientific papers on ArXiv."""

    def __init__(self, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)

    @property
    def name(self) -> str:
        return "arxiv"

    @property
    def source_type(self) -> SourceType:
        return SourceType.ARXIV

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        # Query ArXiv API
        url = (
            "http://export.arxiv.org/api/query?"
            "search_query=cat:cs.AI+AND+all:agent&"
            "start=0&max_results=10&"
            "sortBy=submittedDate&sortOrder=descending"
        )
        xml_text = self._http_get_text(url)
        
        if not xml_text:
            return result
            
        try:
            root = ET.fromstring(xml_text)
            # ArXiv API uses Atom XML namespaces
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            scanned = 0
            
            for entry in root.findall("atom:entry", ns):
                if scanned >= self._max_pages:
                    break
                    
                title = entry.find("atom:title", ns).text if entry.find("atom:title", ns) is not None else ""
                title = title.replace("\n", " ").strip()
                
                summary = entry.find("atom:summary", ns).text if entry.find("atom:summary", ns) is not None else ""
                summary = summary.replace("\n", " ").strip()
                
                pdf_link = ""
                for link in entry.findall("atom:link", ns):
                    if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                        pdf_link = link.get("href") or ""
                        
                paper_id = entry.find("atom:id", ns).text if entry.find("atom:id", ns) is not None else ""
                
                content = (
                    f"Paper Title: {title}\n"
                    f"ArXiv ID: {paper_id}\n"
                    f"Abstract: {summary}\n"
                    f"PDF Link: {pdf_link}\n"
                )
                
                disc = self._make_discovery(
                    source_url=pdf_link or paper_id,
                    title=f"ArXiv Paper: {title}",
                    content=content,
                    category=DiscoveryCategory.PAPER,
                    relevance_score=6.8,
                    metadata={"arxiv_id": paper_id, "pdf_url": pdf_link}
                )
                result.discoveries.append(disc)
                scanned += 1
            result.pages_scanned = 1
        except Exception as e:
            result.errors.append(f"ArXiv XML parse failed: {e}")
            
        return result
