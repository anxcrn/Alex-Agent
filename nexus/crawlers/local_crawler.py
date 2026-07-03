"""Local folder crawler for Project Nexus.

Scans the local <alex_home>/nexus/incoming directory for files (skills, tools,
MCP configurations, etc.) dropped by the user. This allows Nexus to learn
completely offline without any internet connection.
"""

import os
import time
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from alex_constants import get_alex_home
from nexus.crawlers.base import BaseCrawler, CrawlResult, Discovery, DiscoveryCategory, SourceType

logger = logging.getLogger(__name__)

class LocalFolderCrawler(BaseCrawler):
    """Scans local folder for offline learning and discovery."""

    def __init__(self, max_pages: int = 50):
        super().__init__(max_pages=max_pages, request_delay=0.0)

    @property
    def name(self) -> str:
        return "local_folder"

    @property
    def source_type(self) -> SourceType:
        return SourceType.LOCAL

    def crawl(self) -> CrawlResult:
        result = CrawlResult(crawler_name=self.name, source_type=self.source_type)
        
        incoming_dir = get_alex_home() / "nexus" / "incoming"
        processed_dir = incoming_dir / "processed"
        
        # Ensure directories exist
        incoming_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # List files in incoming_dir (exclude directories like 'processed')
            files = [f for f in incoming_dir.iterdir() if f.is_file()]
            
            # Sort by modification time so we process in order
            files.sort(key=lambda f: f.stat().st_mtime)
            
            # Limit to max_pages
            files = files[:self._max_pages]
            result.pages_scanned = len(files)
            
            for file_path in files:
                try:
                    logger.info("[Nexus/LocalCrawler] Processing local file: %s", file_path.name)
                    
                    # Read content
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    
                    # Determine category based on file extension or content
                    ext = file_path.suffix.lower()
                    if ext == ".py":
                        category = DiscoveryCategory.TOOL
                    elif ext == ".md":
                        category = DiscoveryCategory.SKILL
                    elif ext == ".json" and "mcp" in file_path.name.lower():
                        category = DiscoveryCategory.MCP_SERVER
                    else:
                        category = DiscoveryCategory.TECHNIQUE
                        
                    # Create discovery
                    disc = self._make_discovery(
                        source_url=file_path.as_uri(),
                        title=file_path.stem.replace("_", " ").title(),
                        content=content,
                        category=category,
                        relevance_score=10.0,  # Local files are highly relevant by default
                        metadata={"filename": file_path.name, "file_size": file_path.stat().st_size}
                    )
                    
                    result.discoveries.append(disc)
                    
                    # Move to processed folder to avoid reprocessing next time
                    dest_path = processed_dir / file_path.name
                    if dest_path.exists():
                        # Add timestamp to avoid overwrite conflicts
                        timestamp = int(time.time())
                        dest_path = processed_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
                        
                    shutil.move(str(file_path), str(dest_path))
                    logger.info("[Nexus/LocalCrawler] Moved %s to %s", file_path.name, dest_path.name)
                    
                except Exception as file_err:
                    err_msg = f"Error processing file {file_path.name}: {file_err}"
                    logger.error("[Nexus/LocalCrawler] " + err_msg)
                    result.errors.append(err_msg)
                    
        except Exception as e:
            err_msg = f"Failed to list directory {incoming_dir}: {e}"
            logger.error("[Nexus/LocalCrawler] " + err_msg)
            result.errors.append(err_msg)
            
        return result
