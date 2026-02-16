import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.analyzer import _classify_items, _find_connections, analyze
from src.models import (
    AnalyzedItem,
    CrawledContent,
    CrawlerOutput,
    RawTweet,
    ScoredTweet,
    Settings,
    TweetAuthor,
    TweetWithContent,
    WorkNotebook,
)


def _make_settings():
    return Settings(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
        seed_keywords=["LLM"],
        openai_model="gpt-4o-mini",
        openai_max_tokens=1024,
    )


def _make_crawler_output(n=2):
    enriched = []
    for i in range(n):
        enriched.append(
            TweetWithContent(
                scored_tweet=ScoredTweet(
                    tweet=RawTweet(
                        id=f"t{i}",
                        text=f"Tweet {i} about AI",
                        author=TweetAuthor(
                            id=f"a{i}", username=f"user{i}", name=f"User {i}"
                        ),
                        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    ),
                    engagement_score=float(i * 10),
                ),
                crawled_contents=[
                    CrawledContent(
                        source_url=f"https://example.com/{i}",
                        source_type="blog",
                        title=f"Blog {i}",
                        content=f"Content about AI topic {i}",
                    )
                ],
            )
        )
    return CrawlerOutput(enriched_tweets=enriched, all_crawled=[])


def _mock_openai_response(content_dict):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    return mock_response


def test_classify_items_parses_response():
    classify_response = {
        "items": [
            {
                "tweet_id": "t0",
                "category": "research",
                "why_it_matters": "Important finding",
                "key_findings": ["finding1"],
                "reference_links": ["https://example.com/0"],
            },
            {
                "tweet_id": "t1",
                "category": "tooling",
                "why_it_matters": "New tool",
                "key_findings": ["finding2"],
                "reference_links": [],
            },
        ]
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        classify_response
    )

    settings = _make_settings()
    crawler_output = _make_crawler_output(2)
    items = _classify_items(mock_client, crawler_output, settings)

    assert len(items) == 2
    assert items[0].tweet_id == "t0"
    assert items[0].category == "research"
    assert items[1].category == "tooling"


def test_find_connections_backfills_related_ids():
    items = [
        AnalyzedItem(
            tweet_id="t0",
            category="research",
            why_it_matters="x",
            key_findings=["f1"],
        ),
        AnalyzedItem(
            tweet_id="t1",
            category="research",
            why_it_matters="y",
            key_findings=["f2"],
        ),
    ]
    conn_response = {
        "connections": [
            {"item_ids": ["t0", "t1"], "relationship": "Both about research"}
        ]
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        conn_response
    )

    settings = _make_settings()
    connections = _find_connections(mock_client, items, settings)

    assert len(connections) == 1
    assert "t1" in items[0].related_tweet_ids
    assert "t0" in items[1].related_tweet_ids


def test_find_connections_returns_empty_for_single_item():
    items = [
        AnalyzedItem(
            tweet_id="t0",
            category="research",
            why_it_matters="x",
            key_findings=["f1"],
        ),
    ]
    mock_client = MagicMock()
    connections = _find_connections(mock_client, items, _make_settings())
    assert connections == []
    mock_client.chat.completions.create.assert_not_called()


def test_analyze_end_to_end():
    classify_resp = {
        "items": [
            {
                "tweet_id": "t0",
                "category": "research",
                "why_it_matters": "test",
                "key_findings": ["f"],
                "reference_links": [],
            }
        ]
    }
    conn_resp = {"connections": []}

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_openai_response(classify_resp),
        _mock_openai_response(conn_resp),
    ]

    with patch("pipeline.analyzer.OpenAI", return_value=mock_client):
        result = analyze(
            _make_crawler_output(1),
            _make_settings(),
            WorkNotebook(run_date=datetime.now(timezone.utc)),
        )

    assert len(result.items) == 1
    assert result.items[0].category == "research"
