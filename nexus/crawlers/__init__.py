"""Nexus crawlers package — source discovery for self-evolution."""

from nexus.crawlers.base import (
    BaseCrawler,
    CrawlResult,
    Discovery,
    DiscoveryCategory,
    SourceType,
)
from nexus.crawlers.local_crawler import LocalFolderCrawler

__all__ = [
    "BaseCrawler",
    "CrawlResult",
    "Discovery",
    "DiscoveryCategory",
    "SourceType",
    "LocalFolderCrawler",
]

