from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.blog_collector import (
    _discover_feed,
    _get_feed_entry_content,
    _parse_feed_date,
    collect_blogs,
)
from src.models import Settings, WorkNotebook


def _make_settings():
    return Settings(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
        blog_sources=["https://example.com/blog"],
        content_max_chars_blog=3000,
    )


def test_parse_feed_date_with_published_parsed():
    entry = MagicMock()
    entry.published_parsed = (2024, 1, 15, 12, 0, 0, 0, 15, 0)
    entry.updated_parsed = None
    result = _parse_feed_date(entry)
    assert result is not None
    assert result.year == 2024


def test_parse_feed_date_returns_none_when_no_date():
    entry = MagicMock()
    entry.published_parsed = None
    entry.updated_parsed = None
    result = _parse_feed_date(entry)
    assert result is None


def test_get_feed_entry_content_from_summary():
    entry = MagicMock()
    entry.content = []
    entry.summary = "<p>Hello <b>world</b></p>"
    result = _get_feed_entry_content(entry)
    assert "Hello" in result
    assert "world" in result
    assert "<p>" not in result


def test_get_feed_entry_content_from_content():
    entry = MagicMock()
    entry.content = [{"value": "<p>Full content here</p>"}]
    result = _get_feed_entry_content(entry)
    assert "Full content here" in result


def test_collect_blogs_handles_errors():
    settings = _make_settings()
    notebook = WorkNotebook(run_date=datetime.now(timezone.utc))

    with patch("src.blog_collector._fetch_blog_posts", side_effect=Exception("fail")):
        result = collect_blogs(settings, notebook)

    assert len(result.posts) == 0
    assert len(result.errors) == 1
    assert "fail" in result.errors[0]
    assert len(notebook.blog_errors) == 1


def test_collect_blogs_empty_sources():
    settings = Settings(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
        blog_sources=[],
    )
    notebook = WorkNotebook(run_date=datetime.now(timezone.utc))
    result = collect_blogs(settings, notebook)
    assert result.posts == []
    assert result.errors == []
