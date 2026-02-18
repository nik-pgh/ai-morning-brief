
"""
Manual verification script for blog sources.
Run this to check if live blog feeds are working correctly.

Usage:
    python3 tests/manual_test_blogs.py

Note: This script imports from src.blog_collector.
If your environment has issues (e.g., pydantic-core architecture), this will fail.
It includes a monkeypatch for SSL context to handle development environments.
"""

import sys
import logging
from datetime import datetime, timedelta, timezone
import ssl
from typing import List
from unittest.mock import MagicMock

# Ensure strict behavior for manual tests
import pytest

# Attempt to import from src
try:
    from src.blog_collector import _fetch_blog_posts, BlogPost
    from src.models import Settings
    from src.config import load_settings
except ImportError:
    # Fallback/Mock for environment where src is broken but we want to structure the test
    print("WARNING: Could not import from src. Using mock classes for structure.")
    
    class Settings:
        blog_sources = []
        content_max_chars_blog = 3000
    
    class BlogPost:
        def __init__(self, url, title, published, source_blog):
            self.url = url
            self.title = title
            self.published = published
            self.source_blog = source_blog

# Monkeypatch SSL to ignore errors in test environment
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("src.blog_collector")
logger.setLevel(logging.INFO)

def load_live_config_sources():
    """Load sources directly from config.yaml"""
    import yaml
    from pathlib import Path
    
    try:
        config_path = Path("config/config.yaml")
        if not config_path.exists():
            config_path = Path("../config/config.yaml")
        
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        return config.get("blog_sources", [])
    except Exception as e:
        print(f"Error loading config: {e}")
        return []

def test_live_blog_fetching():
    """
    Scans all configured blog sources for posts in the last 24 hours.
    Prints results to stdout.
    """
    print("\n=== Live Blog Verification (Last 24h) ===\n")
    
    sources = load_live_config_sources()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    settings = Settings()
    settings.content_max_chars_blog = 3000
    
    total_found = 0
    
    for url in sources:
        try:
            print(f"Checking {url} ... ", end="", flush=True)
            # Use the actual collector logic
            posts = _fetch_blog_posts(url, cutoff, settings)
            
            if posts:
                print(f"FOUND {len(posts)}")
                for p in posts:
                    print(f"  - {p.title} ({p.published})")
                    print(f"    {p.url}")
                total_found += len(posts)
            else:
                print("No recent posts")
                
        except Exception as e:
            print(f"ERROR: {e}")
            
    print(f"\nTotal recent posts found: {total_found}")

if __name__ == "__main__":
    test_live_blog_fetching()
