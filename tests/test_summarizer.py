from src.summarizer import _parse_sections


def test_parse_sections_basic():
    md = """# Keywords
LLM, GPT, RAG

# Summary
### Item 1
Some summary text

# Connections
- A relates to B

# Further Reading
- [link](url) description"""

    result = _parse_sections(md)
    assert "keywords" in result
    assert "LLM" in result["keywords"]
    assert "summary" in result
    assert "Item 1" in result["summary"]
    assert "connections" in result
    assert "further reading" in result


def test_parse_sections_empty():
    result = _parse_sections("")
    assert result == {}


def test_parse_sections_single():
    md = "# Keywords\nLLM, GPT"
    result = _parse_sections(md)
    assert result == {"keywords": "LLM, GPT"}


def test_parse_sections_preserves_content():
    md = "# Summary\nLine 1\nLine 2\nLine 3"
    result = _parse_sections(md)
    assert "Line 1\nLine 2\nLine 3" == result["summary"]
