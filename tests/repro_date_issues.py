
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import time
from src.blog_collector import _parse_feed_date, _scrape_index, Settings

# 1. Test _parse_feed_date bug
def test_parse_feed_date_timezone():
    # Construct a struct_time that represents 2023-01-01 12:00:00 UTC
    # tm_isdst=0 usually for UTC
    ts = (2023, 1, 1, 12, 0, 0, 6, 1, 0)
    
    # Mock entry
    entry = MagicMock()
    entry.published_parsed = ts
    entry.updated_parsed = None
    
    # _parse_feed_date uses time.mktime() which interprets the tuple as LOCAL time
    # invalidating it against UTC. 
    # If local timezone is not UTC, the result converted back to UTC will be shifted.
    
    dt = _parse_feed_date(entry)
    
    # Expected: 2023-01-01 12:00:00+00:00
    expected = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    print(f"Parsed: {dt}")
    print(f"Expected: {expected}")
    
    assert dt == expected, f"Date mismatch! Got {dt}, expected {expected}"
    print("SUCCESS: Date parsed correctly with UTC handling.")

# 2. Test _scrape_index fallback missing dates
@patch('src.blog_collector.requests.get')
@patch('src.blog_collector._fetch_page_content')
def test_scrape_index_no_date_check(mock_fetch, mock_get):
    settings = Settings(
        twitter_bearer_token="mock",
        openai_api_key="mock",
        discord_webhook_url="mock"
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # Mock index page
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = """
    <html>
        <body>
            <a href="/old-post">Old Post</a>
            <a href="/new-post">New Post</a>
        </body>
    </html>
    """
    
    # Mock content fetch to return different dates
    def side_effect(url, settings):
        if "old-post" in url:
            # Return date older than cutoff
            return "Old content", cutoff - timedelta(hours=1)
        else:
            # Return date newer than cutoff
            return "New content", cutoff + timedelta(hours=1)
            
    mock_fetch.side_effect = side_effect
    
    # Expectation: _scrape_index should now filter out the old post
    
    posts = _scrape_index("https://example.com/blog", cutoff, settings)
    
    print(f"Found {len(posts)} posts")
    for p in posts:
        print(f"Post: {p.url}, Published: {p.published}")
        
    assert len(posts) == 1, f"Expected 1 post, got {len(posts)}"
    assert posts[0].url.endswith("/new-post"), "Expected only new post"
    print("SUCCESS: Old post filtered out.")

if __name__ == "__main__":
    print("--- Test Parse Feed Date ---")
    test_parse_feed_date_timezone()
    print("\n--- Test Scrape Index ---")
    try:
        test_scrape_index_no_date_check()
    except Exception as e:
        print(e)
