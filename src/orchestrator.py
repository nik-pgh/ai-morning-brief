import logging
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path

from src.config import load_settings
from src.models import ContentItem, RawTweet, WorkNotebook

logger = logging.getLogger("ai_morning_brief")


def run_pipeline(dry_run: bool = False) -> None:
    logger.info("Starting AI Morning Brief v2 pipeline")

    settings = load_settings()
    notebook = WorkNotebook(run_date=datetime.now(timezone.utc))

    # Stage 1: Collect tweets
    try:
        logger.info("Stage 1/6: Collecting tweets")
        from src.collector import collect

        collector_output = collect(settings, notebook)
        logger.info(f"Collected {len(collector_output.tweets)} tweets")
    except Exception as e:
        logger.error(f"Twitter collector failed: {e}")
        return

    # Rank tweets — keep top 10 by engagement
    ranked_tweets = _rank_tweets(collector_output.tweets, top_n=10)
    logger.info(
        f"Ranked tweets: kept top {len(ranked_tweets)} "
        f"of {len(collector_output.tweets)}"
    )

    # Stage 2: Collect blog posts
    try:
        logger.info("Stage 2/6: Collecting blog posts")
        from src.blog_collector import collect_blogs

        blog_output = collect_blogs(settings, notebook)
        logger.info(f"Collected {len(blog_output.posts)} blog posts")

        # Log blog errors to file
        if blog_output.errors:
            _log_blog_errors(blog_output.errors)
    except Exception as e:
        logger.error(f"Blog collector failed: {e}")
        notebook.stage_errors["blog_collector"] = str(e)
        # Continue without blog posts
        from src.models import BlogCollectorOutput

        blog_output = BlogCollectorOutput(posts=[], errors=[str(e)])

    # Stage 3: Merge into ContentItems + crawl reference links
    try:
        logger.info("Stage 3/6: Merging content and crawling references")
        content_items = _build_content_items(ranked_tweets, blog_output)
        logger.info(f"Built {len(content_items)} content items")

        from src.crawler import crawl_references

        content_items = crawl_references(content_items, settings, notebook)
    except Exception as e:
        logger.error(f"Crawler failed: {e}")
        notebook.stage_errors["crawler"] = str(e)
        # Continue with uncrawled items
        content_items = _build_content_items(ranked_tweets, blog_output)

    if not content_items:
        logger.warning("No content items found. Aborting pipeline.")
        return

    # Stage 4: Analyze (summarize blogs → semantic analysis → insights)
    try:
        logger.info("Stage 4/6: Analyzing content")
        from src.analyzer import analyze

        analyzer_output = analyze(content_items, settings, notebook)
        logger.info(
            f"Analyzed: {len(analyzer_output.summaries)} blog summaries, "
            f"{len(analyzer_output.semantic_analysis.discussion_points)} discussion points, "
            f"narrative {len(analyzer_output.narrative)} chars"
        )
    except Exception as e:
        logger.error(f"Analyzer failed: {e}")
        return

    # Stage 5: Build digest
    try:
        logger.info("Stage 5/6: Building digest")
        from src.digest import build_digest

        digest_output = build_digest(analyzer_output, content_items, settings)
    except Exception as e:
        logger.error(f"Digest failed: {e}")
        return

    # Stage 6: Deliver
    if dry_run:
        logger.info("Dry run — skipping delivery")
        print(digest_output.full_markdown)
        return

    try:
        logger.info("Stage 6/6: Delivering to Discord")
        from src.delivery import deliver

        deliver(digest_output, settings)
        logger.info("Pipeline complete")
    except Exception as e:
        logger.error(f"Delivery failed: {e}")
        notebook.stage_errors["delivery"] = str(e)


def _rank_tweets(tweets: list[RawTweet], top_n: int = 10) -> list[RawTweet]:
    """Rank tweets by engagement (retweet + reply + like + quote) and return top N."""
    scored = sorted(
        tweets,
        key=lambda t: t.retweet_count + t.reply_count + t.like_count + t.quote_count,
        reverse=True,
    )
    return scored[:top_n]


def _build_content_items(ranked_tweets, blog_output) -> list[ContentItem]:
    items: list[ContentItem] = []

    # Convert ranked tweets to ContentItems
    for tweet in ranked_tweets:
        items.append(
            ContentItem(
                id=f"tweet_{tweet.id}",
                source_type="twitter",
                title=f"@{tweet.author.username}",
                content=tweet.text,
                author=tweet.author.username,
                url=f"https://x.com/{tweet.author.username}/status/{tweet.id}",
                published=tweet.created_at,
                reference_links=tweet.urls,
            )
        )

    # Convert blog posts to ContentItems
    for post in blog_output.posts:
        post_id = md5(post.url.encode()).hexdigest()[:12]
        items.append(
            ContentItem(
                id=f"blog_{post_id}",
                source_type="blog",
                title=post.title,
                content=post.content,
                author="",
                url=post.url,
                published=post.published,
                reference_links=[],
            )
        )

    return items


def _log_blog_errors(errors: list[str]) -> None:
    error_file = Path("blog_errors.txt")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(error_file, "a") as f:
        f.write(f"\n--- {timestamp} ---\n")
        for error in errors:
            f.write(f"{error}\n")
    logger.info(f"Blog errors logged to {error_file}")
