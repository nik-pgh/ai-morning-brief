from src.crawler import _classify_url, _extract_arxiv_id


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
