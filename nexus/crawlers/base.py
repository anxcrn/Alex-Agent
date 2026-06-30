"""Base crawler abstract class for Nexus source crawlers.

All crawlers inherit from BaseCrawler and implement the crawl() method
to discover new tools, skills, MCP servers, and knowledge from their
respective sources.
"""

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Enumeration of discovery source types."""
    GITHUB = "github"
    MCP_REGISTRY = "mcp_registry"
    PYPI = "pypi"
    NPM = "npm"
    REDDIT = "reddit"
    HACKERNEWS = "hackernews"
    YOUTUBE = "youtube"
    ARXIV = "arxiv"
    WEB = "web"
    DOCS = "docs"


class DiscoveryCategory(Enum):
    """Category of a discovered item."""
    SKILL = "skill"
    TOOL = "tool"
    MCP_SERVER = "mcp_server"
    TECHNIQUE = "technique"
    API = "api"
    LIBRARY = "library"
    FRAMEWORK = "framework"
    PAPER = "paper"
    TUTORIAL = "tutorial"
    UNKNOWN = "unknown"


@dataclass
class Discovery:
    """A single item discovered by a crawler.

    Represents a raw finding before analysis — could be a GitHub repo,
    an MCP server listing, a Reddit post, a YouTube video, etc.
    """
    source_type: SourceType
    source_url: str
    title: str
    content: str
    category: DiscoveryCategory = DiscoveryCategory.UNKNOWN
    relevance_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    discovered_at: str = ""
    content_hash: str = ""

    def __post_init__(self):
        if not self.discovered_at:
            from datetime import datetime, timezone
            self.discovered_at = datetime.now(timezone.utc).isoformat()
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute SHA-256 hash of the content for deduplication."""
        text = f"{self.source_url}|{self.title}|{self.content[:2000]}"
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


@dataclass
class CrawlResult:
    """Result of a single crawl operation."""
    crawler_name: str
    source_type: SourceType
    discoveries: List[Discovery] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    pages_scanned: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            from datetime import datetime, timezone
            self.timestamp = datetime.now(timezone.utc).isoformat()


class BaseCrawler(ABC):
    """Abstract base class for all Nexus source crawlers.

    Subclasses must implement:
        - crawl() -> CrawlResult
        - name (property)
        - source_type (property)

    The base class provides:
        - Rate limiting
        - Error handling and logging
        - Content hashing for dedup
        - Retry logic with exponential backoff
    """

    def __init__(self, max_pages: int = 20, request_delay: float = 1.0):
        """Initialize the base crawler.

        Args:
            max_pages: Maximum pages/items to scan per crawl cycle.
            request_delay: Minimum seconds between HTTP requests (rate limiting).
        """
        self._max_pages = max_pages
        self._request_delay = request_delay
        self._last_request_time: float = 0.0

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this crawler."""

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """The SourceType enum value for discoveries from this crawler."""

    @abstractmethod
    def crawl(self) -> CrawlResult:
        """Execute a crawl cycle and return discoveries.

        Implementations should:
        1. Fetch data from their source (API, RSS, web page)
        2. Parse relevant items
        3. Create Discovery objects for each finding
        4. Return a CrawlResult with all discoveries

        Use self._rate_limited_request() for HTTP calls.
        Use self._make_discovery() to create Discovery objects.
        """

    def safe_crawl(self) -> CrawlResult:
        """Execute crawl() with full error handling and timing.

        This is the public entry point — callers should use this instead
        of crawl() directly.
        """
        start = time.monotonic()
        try:
            result = self.crawl()
            result.duration_seconds = time.monotonic() - start
            logger.info(
                "[Nexus/%s] Crawl complete: %d discoveries, %d errors, %.1fs",
                self.name, len(result.discoveries), len(result.errors),
                result.duration_seconds,
            )
            return result
        except Exception as e:
            duration = time.monotonic() - start
            logger.error("[Nexus/%s] Crawl failed after %.1fs: %s", self.name, duration, e)
            return CrawlResult(
                crawler_name=self.name,
                source_type=self.source_type,
                errors=[f"Crawl failed: {e}"],
                duration_seconds=duration,
            )

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request_time = time.monotonic()

    def _http_get(self, url: str, headers: Optional[Dict[str, str]] = None,
                  params: Optional[Dict[str, str]] = None,
                  timeout: float = 30.0, retries: int = 3) -> Optional[Dict[str, Any]]:
        """Make a rate-limited HTTP GET request with retry logic.

        Args:
            url: The URL to fetch.
            headers: Optional HTTP headers.
            params: Optional query parameters.
            timeout: Request timeout in seconds.
            retries: Number of retry attempts on failure.

        Returns:
            Parsed JSON response as dict, or None on failure.
        """
        import requests as req_lib

        self._rate_limit()

        for attempt in range(retries):
            try:
                resp = req_lib.get(
                    url, headers=headers, params=params,
                    timeout=timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt < retries - 1:
                    wait = (2 ** attempt) * 0.5
                    logger.debug(
                        "[Nexus/%s] Request failed (attempt %d/%d), retrying in %.1fs: %s",
                        self.name, attempt + 1, retries, wait, e,
                    )
                    time.sleep(wait)
                else:
                    logger.warning("[Nexus/%s] Request failed after %d attempts: %s", self.name, retries, e)
        return None

    def _http_get_text(self, url: str, headers: Optional[Dict[str, str]] = None,
                       params: Optional[Dict[str, str]] = None,
                       timeout: float = 30.0, retries: int = 3) -> Optional[str]:
        """Make a rate-limited HTTP GET request returning raw text.

        Args:
            url: The URL to fetch.
            headers: Optional HTTP headers.
            params: Optional query parameters.
            timeout: Request timeout in seconds.
            retries: Number of retry attempts on failure.

        Returns:
            Response text, or None on failure.
        """
        import requests as req_lib

        self._rate_limit()

        for attempt in range(retries):
            try:
                resp = req_lib.get(
                    url, headers=headers, params=params,
                    timeout=timeout,
                )
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                if attempt < retries - 1:
                    wait = (2 ** attempt) * 0.5
                    logger.debug(
                        "[Nexus/%s] Text request failed (attempt %d/%d), retrying in %.1fs: %s",
                        self.name, attempt + 1, retries, wait, e,
                    )
                    time.sleep(wait)
                else:
                    logger.warning("[Nexus/%s] Text request failed after %d attempts: %s", self.name, retries, e)
        return None

    def _make_discovery(self, source_url: str, title: str, content: str,
                        category: DiscoveryCategory = DiscoveryCategory.UNKNOWN,
                        relevance_score: float = 0.0,
                        metadata: Optional[Dict[str, Any]] = None) -> Discovery:
        """Create a Discovery object with this crawler's source type.

        Convenience method that pre-fills the source_type field.
        """
        return Discovery(
            source_type=self.source_type,
            source_url=source_url,
            title=title,
            content=content,
            category=category,
            relevance_score=relevance_score,
            metadata=metadata or {},
        )
