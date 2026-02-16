from src.digest import _split_for_discord, _split_on_delimiter, build_digest
from src.models import Settings, SummarizerOutput


def _make_settings(**kw):
    defaults = dict(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
        seed_keywords=["LLM"],
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
    summarizer_output = SummarizerOutput(
        keywords_section="LLM, GPT, RAG",
        summaries_section="### Item 1\nSome summary",
        connections_section="- A relates to B",
        further_reading_section="- [link](url) description",
    )
    settings = _make_settings()
    result = build_digest(summarizer_output, settings)

    assert "AI Morning Brief" in result.title
    assert "# Keywords" in result.full_markdown
    assert "# Summary" in result.full_markdown
    assert "# Connections" in result.full_markdown
    assert "# Further Reading" in result.full_markdown
    assert len(result.chunks) >= 1
