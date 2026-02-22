from src.digest import build_digest
from src.models import (
    AnalyzerOutput,
    AttributedPoint,
    ContentItem,
    ContentSummary,
    SemanticAnalysis,
    Settings,
)


def _make_settings(**kw):
    defaults = dict(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
        discord_max_embed_chars=4096,
    )
    defaults.update(kw)
    return Settings(**defaults)


def _make_content_items():
    return [
        ContentItem(
            id="tweet_1",
            source_type="twitter",
            title="@karpathy",
            content="Big news: new LLM just dropped!",
            author="karpathy",
            url="https://x.com/karpathy/status/1",
        ),
        ContentItem(
            id="blog_abc123",
            source_type="blog",
            title="Understanding Transformers",
            content="Full blog content here...",
            author="lilianweng.github.io",
            url="https://lilianweng.github.io/posts/transformers",
        ),
    ]


_SAMPLE_NARRATIVE = (
    "The AI field is having an identity crisis, and honestly it's about time. "
    "Scaling laws are being revised while transformers are being questioned — "
    "and someone on Twitter is very excited about it. The efficiency-first labs "
    "are quietly winning while the megascale bets look shakier by the week. "
    "Pay attention to what's being optimized away, not just what's being added."
)


def _make_analyzer_output(narrative=_SAMPLE_NARRATIVE):
    return AnalyzerOutput(
        summaries=[
            ContentSummary(
                item_id="blog_abc123",
                summary="A concise summary of the transformers post",
                reference_links=["https://arxiv.org/abs/1234"],
            ),
        ],
        semantic_analysis=SemanticAnalysis(
            discussion_points=[AttributedPoint(point="Scaling vs efficiency debate")],
            trends=[AttributedPoint(point="Smaller models getting competitive")],
            food_for_thought=[AttributedPoint(point="Is attention all we need?")],
        ),
        narrative=narrative,
    )


def test_build_digest_title():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )
    assert "AI Morning Brief" in result.title


def test_build_digest_single_chunk():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )
    assert len(result.chunks) == 1


def test_build_digest_narrative_in_output():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )
    # Header prepended: "Analyzed N tweets and N blog posts."
    assert "*Analyzed" in result.full_markdown
    assert _SAMPLE_NARRATIVE in result.full_markdown
    assert result.full_markdown == result.chunks[0]


def test_build_digest_truncates_overlong_narrative():
    long_narrative = "x" * 5000
    result = build_digest(
        _make_analyzer_output(narrative=long_narrative),
        _make_content_items(),
        _make_settings(discord_max_embed_chars=4096),
    )
    assert len(result.chunks[0]) <= 4096
    assert result.chunks[0].endswith("...")
    assert "*Analyzed" in result.chunks[0]


def test_build_digest_no_section_headers():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )
    assert "# Tweets" not in result.full_markdown
    assert "# Blog Posts" not in result.full_markdown
    assert "# Analysis" not in result.full_markdown
    assert "# Insights" not in result.full_markdown
