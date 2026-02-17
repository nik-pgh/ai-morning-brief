from datetime import datetime, timezone

from src.crawler import _classify_url, _extract_arxiv_id, crawl_references
from src.models import ContentItem, Settings, WorkNotebook


# --- _classify_url tests ---

def test_classify_arxiv():
    assert _classify_url("https://arxiv.org/abs/2401.12345") == "arxiv"
    assert _classify_url("https://arxiv.org/pdf/2401.12345") == "arxiv"


def test_classify_github():
    assert _classify_url("https://github.com/user/repo") == "github"
    assert _classify_url("https://github.com/user/repo/tree/main") == "github"


def test_classify_blog():
    assert _classify_url("https://blog.example.com/post") == "blog"
    assert _classify_url("https://huggingface.co/papers") == "blog"


# --- _extract_arxiv_id tests ---

def test_extract_arxiv_id_abs():
    assert _extract_arxiv_id("https://arxiv.org/abs/2401.12345") == "2401.12345"


def test_extract_arxiv_id_pdf():
    assert _extract_arxiv_id("https://arxiv.org/pdf/2401.12345") == "2401.12345"


def test_extract_arxiv_id_invalid():
    assert _extract_arxiv_id("https://example.com/foo") is None


# --- crawl_references tests ---

def test_crawl_references_empty_items():
    notebook = WorkNotebook(run_date=datetime.now(timezone.utc))
    settings = Settings(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
    )
    result = crawl_references([], settings, notebook)
    assert result == []


def test_crawl_references_no_links():
    notebook = WorkNotebook(run_date=datetime.now(timezone.utc))
    settings = Settings(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
    )
    item = ContentItem(
        id="test1",
        source_type="twitter",
        title="Test",
        content="Hello",
        author="user",
        url="https://x.com/test",
        reference_links=[],
    )
    result = crawl_references([item], settings, notebook)
    assert len(result) == 1
    assert result[0].crawled_references == []
