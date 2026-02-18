
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from src.blog_collector import _scrape_index, Settings

@patch('src.blog_collector.requests.get')
@patch('src.blog_collector._fetch_page_content')
def test_scrape_index_filtering(mock_fetch, mock_get):
    settings = Settings(
        twitter_bearer_token="mock",
        openai_api_key="mock",
        discord_webhook_url="mock"
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # Mock index page with various links
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = """
    <html>
        <body>
            <a href="/about">About Us</a>
            <a href="/contact">Contact</a>
            <a href="/terms">Terms of Service</a>
            <a href="/blog/new-feature">New Feature Release</a>
            <a href="/careers">Jobs</a>
        </body>
    </html>
    """
    
    # Mock content fetch
    def side_effect(url, settings):
        if "new-feature" in url:
            # Valid post with recent date
            return "New feature content...", datetime.now(timezone.utc)
        elif "about" in url:
            # Static page, no date
            return "About us content...", None
        elif "contact" in url:
            # Static page, no date
            return "Contact form...", None
        elif "terms" in url:
             # Static page, no date
            return "Terms content...", None
        elif "careers" in url:
            # Static page, no date
            return "Join us...", None
        return "", None

    mock_fetch.side_effect = side_effect
    
    # Run scraper
    posts = _scrape_index("https://example.com", cutoff, settings)
    
    print(f"Found {len(posts)} posts")
    for p in posts:
        print(f" - {p.url} (published: {p.published})")

    # Assertions
    # We expect ONLY the new feature post.
    # The others should be filtered out by URL keywords or missing date.
    
    urls = [p.url for p in posts]
    print(f"Resulting URLs: {urls}")
    
    assert len(posts) == 1, f"Expected 1 post, got {len(posts)}: {urls}"
    assert "new-feature" in posts[0].url, "Expected new-feature post"
    
    # Verify specific reasons for exclusion (implicit by their absence)
    assert not any("about" in u for u in urls), "Should filtered about (keyword/date)"
    assert not any("contact" in u for u in urls), "Should filtered contact (keyword/date)"
    assert not any("terms" in u for u in urls), "Should filtered terms (keyword/date)"
    assert not any("careers" in u for u in urls), "Should filtered careers (keyword/date)"
    
    print("SUCCESS: Filtering works correctly.")

if __name__ == "__main__":
    try:
        test_scrape_index_filtering()
    except Exception as e:
        print(f"FAILED: {e}")
        exit(1)
