from src.digest import _split_for_discord, _split_on_delimiter, build_digest
from src.models import (
    AnalyzerOutput,
    ContentItem,
    ContentSummary,
    Insight,
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


# --- _split_for_discord tests ---

def test_short_text_single_chunk():
    result = _split_for_discord("Hello world", 100)
    assert result == ["Hello world"]


def test_split_on_section_boundaries():
    text = "# Title\nIntro\n# Section 2\nContent"
    result = _split_for_discord(text, 20)
    assert len(result) >= 2


def test_no_chunk_exceeds_max():
    text = "\n# ".join([f"Section {i}\n" + "x" * 200 for i in range(10)])
    text = "# " + text
    result = _split_for_discord(text, 300)
    for chunk in result:
        assert len(chunk) <= 300


# --- _split_on_delimiter tests ---

def test_split_on_delimiter_small_text():
    result = _split_on_delimiter("hello\n\nworld", "\n\n", 100)
    assert result == ["hello\n\nworld"]


def test_split_on_delimiter_breaks_large():
    text = "part1\n\npart2\n\npart3"
    result = _split_on_delimiter(text, "\n\n", 12)
    assert all(len(c) <= 12 for c in result)


# --- build_digest tests ---

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


def _make_analyzer_output():
    return AnalyzerOutput(
        summaries=[
            ContentSummary(
                item_id="blog_abc123",
                summary="A concise summary of the transformers post",
                reference_links=["https://arxiv.org/abs/1234"],
            ),
        ],
        semantic_analysis=SemanticAnalysis(
            discussion_points=["Scaling vs efficiency debate"],
            trends=["Smaller models getting competitive"],
            food_for_thought=["Is attention all we need?"],
        ),
        insights=[
            Insight(
                title="The Efficiency Revolution",
                content="The trend is clear: smaller is the new bigger...",
                source_item_ids=["blog_abc123"],
            ),
        ],
    )


def test_build_digest_structure():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )

    assert "AI Morning Brief" in result.title
    assert "# Tweets" in result.full_markdown
    assert "# Blog Posts" in result.full_markdown
    assert "# Analysis" in result.full_markdown
    assert "# Insights" in result.full_markdown
    assert len(result.chunks) >= 1


def test_tweets_shown_verbatim():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )

    assert "Big news: new LLM just dropped!" in result.full_markdown
    assert "@karpathy" in result.full_markdown
    assert "[Link](https://x.com/karpathy/status/1)" in result.full_markdown


def test_blog_summary_in_output():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )

    assert "Understanding Transformers" in result.full_markdown
    assert "lilianweng.github.io" in result.full_markdown
    assert "A concise summary of the transformers post" in result.full_markdown
    assert "https://arxiv.org/abs/1234" in result.full_markdown


def test_semantic_analysis_in_output():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )

    assert "Discussion Points" in result.full_markdown
    assert "Scaling vs efficiency debate" in result.full_markdown
    assert "Trends" in result.full_markdown
    assert "Food for Thought" in result.full_markdown


def test_insights_no_level_tag():
    result = build_digest(
        _make_analyzer_output(), _make_content_items(), _make_settings()
    )

    assert "The Efficiency Revolution" in result.full_markdown
    # No [TECHNICAL] or [BUSINESS] level tags
    assert "[TECHNICAL]" not in result.full_markdown
    assert "[BUSINESS]" not in result.full_markdown
