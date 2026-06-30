"""MCP registry crawler for discovering Model Context Protocol servers.

Fetches registry listings from the official registry, Smithery, Glama, and mcp.so.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)


class MCPRegistryCrawler(BaseCrawler):
    """Crawler for discovering new MCP servers from registries."""

    def __init__(self, max_pages: int = 20) -> None:
        super().__init__(max_pages=max_pages, request_delay=2.0)

    @property
    def name(self) -> str:
        return "mcp_registry"

    @property
    def source_type(self) -> SourceType:
        return SourceType.MCP_REGISTRY

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        # 1. Crawl Official Registry
        scanned = 0
        try:
            url = "https://registry.modelcontextprotocol.io/v0.1/servers"
            data = self._http_get(url)
            scanned += 1
            if data and "servers" in data:
                for server in data["servers"]:
                    name = server.get("name", "")
                    description = server.get("description", "")
                    github_url = server.get("repository", "")
                    
                    content = (
                        f"MCP Server: {name}\n"
                        f"Description: {description}\n"
                        f"Registry Source: Official Registry\n"
                        f"Install commands: {server.get('packages', [])}\n"
                    )
                    
                    disc = self._make_discovery(
                        source_url=github_url or f"https://registry.modelcontextprotocol.io/servers/{name}",
                        title=f"MCP Server: {name}",
                        content=content,
                        category=DiscoveryCategory.MCP_SERVER,
                        relevance_score=8.0,
                        metadata={
                            "name": name,
                            "registry": "official",
                            "packages": server.get("packages")
                        }
                    )
                    result.discoveries.append(disc)
        except Exception as e:
            result.errors.append(f"Official registry crawl failed: {e}")

        # 2. Crawl Smithery API
        smithery_key = os.environ.get("SMITHERY_API_KEY")
        if smithery_key:
            try:
                headers = {"Authorization": f"Bearer {smithery_key}"}
                url = "https://api.smithery.ai/servers?pageSize=50"
                data = self._http_get(url, headers=headers)
                scanned += 1
                if data and "servers" in data:
                    for server in data["servers"]:
                        name = server.get("name", "")
                        description = server.get("description", "")
                        readme = server.get("readme", "")
                        
                        content = (
                            f"MCP Server: {name}\n"
                            f"Description: {description}\n"
                            f"Registry Source: Smithery.ai\n"
                            f"Readme: {readme[:500]}\n"
                        )
                        
                        disc = self._make_discovery(
                            source_url=f"https://smithery.ai/server/{name}",
                            title=f"Smithery MCP Server: {name}",
                            content=content,
                            category=DiscoveryCategory.MCP_SERVER,
                            relevance_score=7.5,
                            metadata={
                                "name": name,
                                "registry": "smithery",
                                "install_command": f"smithery mcp add {name}"
                            }
                        )
                        result.discoveries.append(disc)
            except Exception as e:
                result.errors.append(f"Smithery crawl failed: {e}")
                
        result.pages_scanned = scanned
        return result
