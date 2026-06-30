"""Reddit crawler for discovering new tools, techniques, and suggestions from LLM subreddits.

Queries the Reddit JSON API (without auth) for subreddits like r/LocalLLaMA.
"""

import logging
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class RedditCrawler(BaseCrawler):
    """Crawler for discovering community recommendations and tools on Reddit."""

    def __init__(self, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)

    @property
    def name(self) -> str:
        return "reddit"

    @property
    def source_type(self) -> SourceType:
        return SourceType.REDDIT

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        subreddits = ["LocalLLaMA", "ChatGPT", "ClaudeAI"]
        headers = {"User-Agent": "NexusCrawler/1.0"}
        scanned = 0
        
        for sub in subreddits:
            if scanned >= self._max_pages:
                break
                
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
            data = self._http_get(url, headers=headers)
            scanned += 1
            
            if not data or "data" not in data or "children" not in data["data"]:
                continue
                
            for child in data["data"]["children"]:
                post = child.get("data", {})
                title = post.get("title", "")
                selftext = post.get("selftext", "")
                post_url = f"https://reddit.com{post.get('permalink')}"
                
                # Check for keywords
                keywords = ["mcp", "agent", "tool", "github repo", "new model"]
                match = any(kw in title.lower() or kw in selftext.lower() for kw in keywords)
                
                if match:
                    content = (
                        f"Subreddit: r/{sub}\n"
                        f"Post Title: {title}\n"
                        f"Score: {post.get('score')}\n"
                        f"Comments: {post.get('num_comments')}\n"
                        f"Text: {selftext[:1000]}\n"
                    )
                    
                    disc = self._make_discovery(
                        source_url=post_url,
                        title=f"Reddit [r/{sub}]: {title}",
                        content=content,
                        category=DiscoveryCategory.TECHNIQUE,
                        relevance_score=6.0,
                        metadata={
                            "subreddit": sub,
                            "score": post.get("score"),
                            "comments": post.get("num_comments")
                        }
                    )
                    result.discoveries.append(disc)
                    
        result.pages_scanned = scanned
        return result
