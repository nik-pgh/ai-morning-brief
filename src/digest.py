import logging
from datetime import datetime

from src.models import AnalyzerOutput, ContentItem, DigestOutput, Settings

logger = logging.getLogger(__name__)


def build_digest(
    analyzer_output: AnalyzerOutput,
    content_items: list[ContentItem],
    settings: Settings,
) -> DigestOutput:
    today = datetime.now().strftime("%B %d, %Y")
    title = f"AI Morning Brief — {today}"

    n_tweets = sum(1 for item in content_items if item.source_type == "twitter")
    n_blogs = sum(1 for item in content_items if item.source_type == "blog")
    tweet_label = "tweets" if n_tweets != 1 else "tweet"
    blog_label = "blog posts" if n_blogs != 1 else "blog post"
    header = f"*Analyzed {n_tweets} {tweet_label} and {n_blogs} {blog_label}.*\n\n"

    narrative = header + analyzer_output.narrative
    if len(narrative) > settings.discord_max_embed_chars:
        narrative = narrative[: settings.discord_max_embed_chars - 3] + "..."

    logger.info(f"Digest: {len(narrative)} chars, 1 chunk")
    return DigestOutput(
        title=title,
        full_markdown=narrative,
        chunks=[narrative],
    )
