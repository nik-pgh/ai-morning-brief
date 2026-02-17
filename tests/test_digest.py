from src.digest import _split_for_discord, _split_on_delimiter, build_digest
from src.models import (
    AnalyzerOutput,
    ContentSummary,
    Insight,
    RelationshipAnalysis,
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

def test_build_digest_structure():
    analyzer_output = AnalyzerOutput(
        summaries=[
            ContentSummary(
                item_id="item_1",
                summary="Summary of item 1",
                reference_links=["https://example.com"],
            ),
        ],
        relationships=[
            RelationshipAnalysis(
                related_item_ids=["item_1", "item_2"],
                relationship="Both about AI",
                strength="strong",
            ),
        ],
        insights=[
            Insight(
                title="AI Trend",
                content="AI is trending because...",
                level="technical",
                source_item_ids=["item_1"],
            ),
        ],
    )
    settings = _make_settings()
    result = build_digest(analyzer_output, settings)

    assert "AI Morning Brief" in result.title
    assert "# Summary" in result.full_markdown
    assert "# Analysis" in result.full_markdown
    assert "# Insights" in result.full_markdown
    assert len(result.chunks) >= 1
