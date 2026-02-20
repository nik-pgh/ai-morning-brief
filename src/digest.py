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

    narrative = analyzer_output.narrative
    if len(narrative) > settings.discord_max_embed_chars:
        narrative = narrative[: settings.discord_max_embed_chars - 3] + "..."

    logger.info(f"Digest: {len(narrative)} chars, 1 chunk")
    return DigestOutput(
        title=title,
        full_markdown=narrative,
        chunks=[narrative],
    )
