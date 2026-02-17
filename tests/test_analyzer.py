import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.analyzer import _summarize_items, _find_relationships, _derive_insights, analyze
from src.models import (
    ContentItem,
    ContentSummary,
    CrawledContent,
    RelationshipAnalysis,
    Settings,
    WorkNotebook,
)


def _make_settings():
    return Settings(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
        openai_model="gpt-4o-mini",
        openai_max_tokens=1024,
        analyzer_batch_size=10,
    )


def _make_content_items(n=2):
    items = []
    for i in range(n):
        items.append(
            ContentItem(
                id=f"item_{i}",
                source_type="twitter",
                title=f"Item {i}",
                content=f"Content about AI topic {i}",
                author=f"user{i}",
                url=f"https://x.com/user{i}/status/{i}",
                crawled_references=[
                    CrawledContent(
                        source_url=f"https://example.com/{i}",
                        source_type="blog",
                        title=f"Blog {i}",
                        content=f"Crawled content {i}",
                    )
                ],
            )
        )
    return items


def _mock_openai_response(content_dict):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    return mock_response


def test_summarize_items_parses_response():
    summarize_response = {
        "summaries": [
            {
                "item_id": "item_0",
                "summary": "Summary of item 0",
                "reference_links": ["https://example.com/0"],
            },
            {
                "item_id": "item_1",
                "summary": "Summary of item 1",
                "reference_links": [],
            },
        ]
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        summarize_response
    )

    settings = _make_settings()
    items = _make_content_items(2)
    summaries = _summarize_items(mock_client, items, settings)

    assert len(summaries) == 2
    assert summaries[0].item_id == "item_0"
    assert summaries[0].summary == "Summary of item 0"
    assert summaries[1].item_id == "item_1"


def test_find_relationships_parses_response():
    summaries = [
        ContentSummary(item_id="item_0", summary="About LLMs"),
        ContentSummary(item_id="item_1", summary="About LLMs too"),
    ]
    rel_response = {
        "relationships": [
            {
                "related_item_ids": ["item_0", "item_1"],
                "relationship": "Both discuss LLMs",
                "strength": "strong",
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        rel_response
    )

    settings = _make_settings()
    relationships = _find_relationships(mock_client, summaries, settings)

    assert len(relationships) == 1
    assert relationships[0].strength == "strong"
    assert "item_0" in relationships[0].related_item_ids


def test_find_relationships_returns_empty_for_single_item():
    summaries = [ContentSummary(item_id="item_0", summary="Only one")]
    mock_client = MagicMock()
    relationships = _find_relationships(mock_client, summaries, _make_settings())
    assert relationships == []
    mock_client.chat.completions.create.assert_not_called()


def test_derive_insights_parses_response():
    summaries = [
        ContentSummary(item_id="item_0", summary="About LLMs"),
    ]
    relationships = [
        RelationshipAnalysis(
            related_item_ids=["item_0", "item_1"],
            relationship="Related",
            strength="moderate",
        )
    ]
    insights_response = {
        "insights": [
            {
                "title": "LLM Trend",
                "content": "LLMs are trending because...",
                "level": "technical",
                "source_item_ids": ["item_0"],
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        insights_response
    )

    settings = _make_settings()
    insights = _derive_insights(mock_client, summaries, relationships, settings)

    assert len(insights) == 1
    assert insights[0].title == "LLM Trend"
    assert insights[0].level == "technical"


def test_analyze_empty_items():
    settings = _make_settings()
    notebook = WorkNotebook(run_date=datetime.now(timezone.utc))
    result = analyze([], settings, notebook)
    assert result.summaries == []
    assert result.relationships == []
    assert result.insights == []


def test_analyze_end_to_end():
    summarize_resp = {
        "summaries": [
            {
                "item_id": "item_0",
                "summary": "Test summary about LLMs",
                "reference_links": [],
            },
            {
                "item_id": "item_1",
                "summary": "Test summary about GPT",
                "reference_links": [],
            },
        ]
    }
    rel_resp = {
        "relationships": [
            {
                "related_item_ids": ["item_0", "item_1"],
                "relationship": "Both about language models",
                "strength": "strong",
            }
        ]
    }
    insights_resp = {
        "insights": [
            {
                "title": "Test Insight",
                "content": "Insight content",
                "level": "business",
                "source_item_ids": ["item_0", "item_1"],
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_openai_response(summarize_resp),
        _mock_openai_response(rel_resp),
        _mock_openai_response(insights_resp),
    ]

    with patch("src.analyzer.OpenAI", return_value=mock_client):
        result = analyze(
            _make_content_items(2),
            _make_settings(),
            WorkNotebook(run_date=datetime.now(timezone.utc)),
        )

    assert len(result.summaries) == 2
    assert len(result.relationships) == 1
    assert len(result.insights) == 1
    assert result.insights[0].level == "business"
