import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from src.models import BlogCollectorOutput, BlogPost, Settings, WorkNotebook
import calendar
import ssl

# Fix for SSL certificate errors in some environments (e.g., macOS Python)
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context


logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (AI Morning Brief Bot)"
FEED_PATHS = ["/feed", "/rss", "/atom.xml", "/feed.xml", "/index.xml", "/rss.xml"]
SKIPPED_URL_KEYWORDS = [
    "about",
    "contact",
    "terms",
    "privacy",
    "policy",
    "jobs",
    "careers",
    "login",
    "signup",
    "signin",
    "register",
    "subscription",
    "pricing",
]


def collect_blogs(
    settings: Settings, notebook: WorkNotebook
) -> BlogCollectorOutput:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    all_posts: list[BlogPost] = []
    errors: list[str] = []

    for blog_url in settings.blog_sources:
        try:
            posts = _fetch_blog_posts(blog_url, cutoff, settings)
            all_posts.extend(posts)
            if posts:
                logger.info(f"Found {len(posts)} new post(s) from {blog_url}")
            else:
                logger.debug(f"No new posts from {blog_url}")
        except Exception as e:
            msg = f"[{blog_url}] {e}"
            errors.append(msg)
            logger.warning(f"Failed to fetch blog: {msg}")

    notebook.blog_errors = errors
    logger.info(f"Blog collector: {len(all_posts)} posts, {len(errors)} errors")
    return BlogCollectorOutput(posts=all_posts, errors=errors)


def _fetch_blog_posts(
    blog_url: str, cutoff: datetime, settings: Settings
) -> list[BlogPost]:
    feed_url = _discover_feed(blog_url)
    if feed_url:
        return _parse_feed(feed_url, blog_url, cutoff, settings)
    return _scrape_index(blog_url, cutoff, settings)


def _discover_feed(blog_url: str) -> str | None:
    # Try common feed paths first
    for path in FEED_PATHS:
        feed_url = urljoin(blog_url, path)
        try:
            resp = requests.head(
                feed_url,
                timeout=5,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                if any(t in content_type for t in ["xml", "rss", "atom", "text"]):
                    return feed_url
        except requests.RequestException:
            continue

    # Fallback: look for <link rel="alternate"> in HTML
    try:
        resp = requests.get(
            blog_url,
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("link", rel="alternate"):
            link_type = link.get("type", "")
            if "rss" in link_type or "atom" in link_type or "xml" in link_type:
                href = link.get("href", "")
                if href:
                    return urljoin(blog_url, href)
    except requests.RequestException:
        pass

    return None


def _parse_feed(
    feed_url: str, blog_url: str, cutoff: datetime, settings: Settings
) -> list[BlogPost]:
    feed = feedparser.parse(feed_url)
    posts: list[BlogPost] = []

    for entry in feed.entries:
        published = _parse_feed_date(entry)
        if published and published < cutoff:
            continue

        link = entry.get("link", "")
        title = entry.get("title", "")
        content = _get_feed_entry_content(entry)

        # If content is too short, fetch the full page
        if len(content) < 200 and link:
            try:
                content, _ = _fetch_page_content(link, settings)
            except Exception:
                pass

        if title or content:
            posts.append(
                BlogPost(
                    url=link or blog_url,
                    title=title,
                    content=content[: settings.content_max_chars_blog],
                    published=published,
                    source_blog=blog_url,
                )
            )

    return posts


def _parse_feed_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                # Use calendar.timegm for UTC tuples to avoid local timezone offset issues
                timestamp = calendar.timegm(parsed)
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return None


def _get_feed_entry_content(entry) -> str:
    # Try content field first (full content), then summary
    if hasattr(entry, "content") and entry.content:
        raw = entry.content[0].get("value", "")
    elif hasattr(entry, "summary"):
        raw = entry.summary
    else:
        return ""

    # Strip HTML tags
    soup = BeautifulSoup(raw, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def _scrape_index(
    blog_url: str, cutoff: datetime, settings: Settings
) -> list[BlogPost]:
    """Fallback: scrape index page for post links and try to find recent ones."""
    try:
        resp = requests.get(
            blog_url,
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    domain = urlparse(blog_url).hostname

    # Find article-like links
    posts: list[BlogPost] = []
    seen_urls: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = urljoin(blog_url, link["href"])
        parsed = urlparse(href)

        # Only follow links on the same domain
        if parsed.hostname != domain:
            continue
        # Skip anchors and non-article paths
        if href in seen_urls or href == blog_url:
            continue
        if any(skip in href for skip in ["#", "?", "/tag/", "/category/", "/page/"]):
            continue
        
        # Skip common non-article pages
        if any(keyword in href.lower() for keyword in SKIPPED_URL_KEYWORDS):
            continue
            
        # Skip root page (handling trailing slashes)
        if parsed.path.strip("/") == "":
            continue

        seen_urls.add(href)

        # Limit to first 5 links to avoid crawling entire archives
        if len(posts) >= 5:
            break

        try:
            content, published = _fetch_page_content(href, settings)
            
            # STRICT REQUIREMENT: Must have a valid date
            if not published:
                continue
                
            # If we found a date, check if it's recent
            if published < cutoff:
                continue
            
            if len(content) > 100:
                title = link.get_text(strip=True) or href
                posts.append(
                    BlogPost(
                        url=href,
                        title=title,
                        content=content[: settings.content_max_chars_blog],
                        published=published,
                        source_blog=blog_url,
                    )
                )
        except Exception:
            continue

    return posts


def _fetch_page_content(url: str, settings: Settings) -> tuple[str, datetime | None]:
    resp = requests.get(
        url,
        timeout=10,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    
    published = _extract_date_from_html(resp.text)

    try:
        import trafilatura
        text = trafilatura.extract(
            resp.text, include_comments=False, include_tables=False
        )
        if text:
            # Trafilatura might also extract date, but we use our metadata extractor for now
            return text, published
    except ImportError:
        pass

    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("article") or soup.find("main") or soup.find("body")
    if main:
        return main.get_text(separator="\n", strip=True), published
    return "", published


def _extract_date_from_html(html: str) -> datetime | None:
    """Attempt to extract publication date from HTML meta tags."""
    try:
        import trafilatura
        # Use trafilatura's robust date extraction if available
        qs = trafilatura.extract_metadata(html)
        if qs and qs.date:
            try:
                dt = datetime.fromisoformat(qs.date)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
    except ImportError:
        pass

    # Fallback to manual meta tag inspection using BeautifulSoup
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Common meta tags for publication date
        meta_tags = [
            {"property": "article:published_time"},
            {"property": "og:published_time"},
            {"name": "date"},
            {"name": "publish-date"},
            {"name": "dcterms.created"},
            {"itemprop": "datePublished"},
        ]
        
        for tags in meta_tags:
            meta = soup.find("meta", **tags)
            if meta:
                content = meta.get("content", "")
                if content:
                    # Very basic ISO parsing, might need dateutil for robust parsing
                    # but attempting to keep deps minimal if dateutil isn't guaranteed
                    try:
                        # Handle basic ISO format YYYY-MM-DD...
                        if "T" in content:
                            dt = datetime.fromisoformat(content.replace("Z", "+00:00"))
                        else:
                            # Try simple YYYY-MM-DD
                            dt = datetime.strptime(content[:10], "%Y-%m-%d")
                            dt = dt.replace(tzinfo=timezone.utc)
                            
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except ValueError:
                        continue
    except Exception:
        pass
        
    return None
