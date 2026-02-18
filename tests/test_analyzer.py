import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.analyzer import _summarize_blog_posts, _semantic_analysis, _derive_insights, analyze
from src.models import (
    ContentItem,
    ContentSummary,
    CrawledContent,
    SemanticAnalysis,
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


def _make_content_items():
    """Create a mix of twitter and blog items."""
    return [
        ContentItem(
            id="tweet_1",
            source_type="twitter",
            title="@karpathy",
            content="Exciting new LLM architecture just dropped!",
            author="karpathy",
            url="https://x.com/karpathy/status/1",
        ),
        ContentItem(
            id="blog_abc123",
            source_type="blog",
            title="Understanding Transformers",
            content="A deep dive into transformer architecture...",
            author="lilianweng.github.io",
            url="https://lilianweng.github.io/posts/transformers",
            crawled_references=[
                CrawledContent(
                    source_url="https://arxiv.org/abs/1234",
                    source_type="arxiv",
                    title="Attention Paper",
                    content="Attention is all you need...",
                )
            ],
        ),
        ContentItem(
            id="blog_def456",
            source_type="blog",
            title="Scaling Laws Revisited",
            content="New findings on scaling laws...",
            author="openai.com",
            url="https://openai.com/blog/scaling-laws",
        ),
    ]


def _mock_openai_response(content_dict):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    return mock_response


def test_summarize_blog_posts_individual_calls():
    """One LLM call per blog post, tweets are skipped."""
    blog1_resp = {
        "item_id": "blog_abc123",
        "summary": "Summary of transformers post",
        "reference_links": ["https://arxiv.org/abs/1234"],
    }
    blog2_resp = {
        "item_id": "blog_def456",
        "summary": "Summary of scaling laws",
        "reference_links": [],
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_openai_response(blog1_resp),
        _mock_openai_response(blog2_resp),
    ]

    settings = _make_settings()
    items = _make_content_items()
    summaries = _summarize_blog_posts(mock_client, items, settings)

    assert len(summaries) == 2
    assert summaries[0].item_id == "blog_abc123"
    assert summaries[1].item_id == "blog_def456"
    # Should be called once per blog post (2 blogs, not 3 items)
    assert mock_client.chat.completions.create.call_count == 2


def test_summarize_blog_posts_skips_tweets_only():
    """When all items are tweets, no LLM calls are made."""
    mock_client = MagicMock()
    items = [
        ContentItem(
            id="tweet_1",
            source_type="twitter",
            title="@user",
            content="Tweet text",
            author="user",
            url="https://x.com/user/status/1",
        )
    ]
    summaries = _summarize_blog_posts(mock_client, items, _make_settings())
    assert summaries == []
    mock_client.chat.completions.create.assert_not_called()


def test_semantic_analysis_parses_response():
    summaries = [
        ContentSummary(item_id="blog_abc123", summary="About transformers"),
    ]
    items = _make_content_items()
    analysis_response = {
        "discussion_points": ["Scaling vs architecture innovation"],
        "trends": ["Smaller models getting competitive"],
        "food_for_thought": ["Are we hitting a wall?"],
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        analysis_response
    )

    result = _semantic_analysis(mock_client, items, summaries, _make_settings())

    assert isinstance(result, SemanticAnalysis)
    assert len(result.discussion_points) == 1
    assert len(result.trends) == 1
    assert len(result.food_for_thought) == 1
    assert "Scaling" in result.discussion_points[0]


def test_derive_insights_parses_response():
    summaries = [
        ContentSummary(item_id="blog_abc123", summary="About transformers"),
    ]
    semantic = SemanticAnalysis(
        discussion_points=["Scaling debate"],
        trends=["Smaller models"],
        food_for_thought=["Walls ahead?"],
    )
    items = _make_content_items()
    insights_response = {
        "insights": [
            {
                "title": "The Great Scaling Debate",
                "content": "Everyone's talking about whether bigger is still better...",
                "source_item_ids": ["blog_abc123"],
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        insights_response
    )

    insights = _derive_insights(mock_client, summaries, semantic, items, _make_settings())

    assert len(insights) == 1
    assert insights[0].title == "The Great Scaling Debate"
    assert insights[0].source_item_ids == ["blog_abc123"]


def test_analyze_empty_items():
    settings = _make_settings()
    notebook = WorkNotebook(run_date=datetime.now(timezone.utc))
    result = analyze([], settings, notebook)
    assert result.summaries == []
    assert result.semantic_analysis.discussion_points == []
    assert result.insights == []


def test_analyze_end_to_end():
    """End-to-end with 2 blog posts: 2 summarize calls + 1 semantic + 1 insights."""
    blog1_resp = {
        "item_id": "blog_abc123",
        "summary": "Transformers summary",
        "reference_links": [],
    }
    blog2_resp = {
        "item_id": "blog_def456",
        "summary": "Scaling laws summary",
        "reference_links": [],
    }
    semantic_resp = {
        "discussion_points": ["Scaling debate"],
        "trends": ["Efficient models"],
        "food_for_thought": ["Rethinking attention"],
    }
    insights_resp = {
        "insights": [
            {
                "title": "Test Insight",
                "content": "Insight content here",
                "source_item_ids": ["blog_abc123", "blog_def456"],
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_openai_response(blog1_resp),   # blog 1 summary
        _mock_openai_response(blog2_resp),   # blog 2 summary
        _mock_openai_response(semantic_resp), # semantic analysis
        _mock_openai_response(insights_resp), # insights
    ]

    with patch("src.analyzer.OpenAI", return_value=mock_client):
        result = analyze(
            _make_content_items(),
            _make_settings(),
            WorkNotebook(run_date=datetime.now(timezone.utc)),
        )

    assert len(result.summaries) == 2
    assert len(result.semantic_analysis.discussion_points) == 1
    assert len(result.insights) == 1
    assert mock_client.chat.completions.create.call_count == 4
