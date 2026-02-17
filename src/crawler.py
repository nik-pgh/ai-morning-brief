import logging
import re
from urllib.parse import urlparse

import requests

from src.models import (
    CrawledContent,
    ContentItem,
    Settings,
    WorkNotebook,
)

logger = logging.getLogger(__name__)


def crawl_references(
    items: list[ContentItem],
    settings: Settings,
    notebook: WorkNotebook,
) -> list[ContentItem]:
    """For each content item, fetch content from its reference links (1 level deep)."""
    for item in items:
        for url in item.reference_links:
            try:
                content = _fetch_url(url, settings)
                if content:
                    item.crawled_references.append(content)
            except Exception as e:
                notebook.stage_errors[f"crawl:{url}"] = str(e)
                logger.warning(f"Failed to crawl {url}: {e}")

    total = sum(len(item.crawled_references) for item in items)
    logger.info(f"Crawled {total} reference links from {len(items)} items")
    return items


def _classify_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    if "arxiv.org" in host:
        return "arxiv"
    if "github.com" in host:
        return "github"
    return "blog"


def _fetch_url(url: str, settings: Settings) -> CrawledContent | None:
    url_type = _classify_url(url)
    if url_type == "arxiv":
        return _fetch_arxiv_paper(url, settings)
    elif url_type == "github":
        return _fetch_github_repo(url, settings)
    else:
        return _fetch_blog(url, settings)


# --- arXiv ---

def _extract_arxiv_id(url: str) -> str | None:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", url)
    return match.group(1) if match else None


def _fetch_arxiv_paper(url: str, settings: Settings) -> CrawledContent | None:
    arxiv_id = _extract_arxiv_id(url)
    if not arxiv_id:
        return None

    import arxiv as arxiv_lib

    client = arxiv_lib.Client()
    search = arxiv_lib.Search(id_list=[arxiv_id])
    results = list(client.results(search))
    if not results:
        return None

    paper = results[0]
    return CrawledContent(
        source_url=url,
        source_type="arxiv",
        title=paper.title,
        content=paper.summary[: settings.content_max_chars_paper],
        metadata={
            "authors": [a.name for a in paper.authors[:5]],
            "published": paper.published.isoformat(),
            "arxiv_id": arxiv_id,
            "categories": list(paper.categories),
        },
    )


# --- GitHub ---

def _fetch_github_repo(url: str, settings: Settings) -> CrawledContent | None:
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)

    headers = {"Accept": "application/vnd.github.v3+json"}
    if settings.github_token:
        headers["Authorization"] = f"token {settings.github_token}"

    repo_resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=headers,
        timeout=10,
    )
    repo_resp.raise_for_status()
    repo_data = repo_resp.json()

    readme_resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/readme",
        headers={**headers, "Accept": "application/vnd.github.v3.raw"},
        timeout=10,
    )
    readme_text = ""
    if readme_resp.status_code == 200:
        readme_text = readme_resp.text[: settings.content_max_chars_readme]

    return CrawledContent(
        source_url=url,
        source_type="github",
        title=repo_data.get("full_name", f"{owner}/{repo}"),
        content=readme_text,
        metadata={
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "language": repo_data.get("language"),
            "description": repo_data.get("description", ""),
        },
    )


# --- Blog ---

def _fetch_blog(url: str, settings: Settings) -> CrawledContent | None:
    resp = requests.get(
        url,
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0 (AI Morning Brief Bot)"},
    )
    resp.raise_for_status()

    text = ""
    title = ""

    try:
        import trafilatura

        downloaded = trafilatura.extract(
            resp.text, include_comments=False, include_tables=False
        )
        if downloaded:
            text = downloaded
    except ImportError:
        pass

    if not text:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string if soup.title else ""
        main = soup.find("article") or soup.find("main") or soup.find("body")
        if main:
            text = main.get_text(separator="\n", strip=True)

    return CrawledContent(
        source_url=url,
        source_type="blog",
        title=title,
        content=text[: settings.content_max_chars_blog],
        metadata={"domain": urlparse(url).hostname},
    )
