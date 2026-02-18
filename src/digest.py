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

    summary_map = {s.item_id: s for s in analyzer_output.summaries}

    # Build Tweets section — full tweet text, verbatim
    tweet_lines = []
    for item in content_items:
        if item.source_type == "twitter":
            tweet_lines.append(f"### @{item.author}")
            tweet_lines.append(item.content)
            tweet_lines.append(f"[Link]({item.url})")
            tweet_lines.append("")

    # Build Blog Posts section — title + author + summary
    blog_lines = []
    for item in content_items:
        if item.source_type == "blog":
            blog_lines.append(f"### {item.title}")
            if item.author:
                blog_lines.append(f"*by {item.author}*")
            s = summary_map.get(item.id)
            if s:
                blog_lines.append(s.summary)
                if s.reference_links:
                    blog_lines.append(
                        "**References:** " + ", ".join(s.reference_links)
                    )
            blog_lines.append("")

    # Build Analysis section — semantic analysis
    analysis_lines = []
    sa = analyzer_output.semantic_analysis
    if sa.discussion_points:
        analysis_lines.append("## Discussion Points")
        for point in sa.discussion_points:
            analysis_lines.append(f"- {point}")
        analysis_lines.append("")
    if sa.trends:
        analysis_lines.append("## Trends")
        for trend in sa.trends:
            analysis_lines.append(f"- {trend}")
        analysis_lines.append("")
    if sa.food_for_thought:
        analysis_lines.append("## Food for Thought")
        for thought in sa.food_for_thought:
            analysis_lines.append(f"- {thought}")
        analysis_lines.append("")

    # Build Insights section
    insight_lines = []
    for ins in analyzer_output.insights:
        insight_lines.append(f"### {ins.title}")
        insight_lines.append(ins.content)
        insight_lines.append("")

    full_markdown = (
        f"# {title}\n\n"
        f"# Tweets\n{chr(10).join(tweet_lines)}\n\n"
        f"# Blog Posts\n{chr(10).join(blog_lines)}\n\n"
        f"# Analysis\n{chr(10).join(analysis_lines)}\n\n"
        f"# Insights\n{chr(10).join(insight_lines)}"
    )

    chunks = _split_for_discord(full_markdown, settings.discord_max_embed_chars)

    logger.info(
        f"Digest: {len(full_markdown)} chars, {len(chunks)} chunk(s)"
    )
    return DigestOutput(
        title=title,
        full_markdown=full_markdown,
        chunks=chunks,
    )


def _split_for_discord(markdown: str, max_chars: int) -> list[str]:
    if len(markdown) <= max_chars:
        return [markdown]

    chunks: list[str] = []
    sections = markdown.split("\n# ")
    current_chunk = ""

    for i, section in enumerate(sections):
        prefix = "# " if i > 0 else ""
        candidate = prefix + section

        if len(current_chunk) + len(candidate) + 1 <= max_chars:
            current_chunk += ("\n" if current_chunk else "") + candidate
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(candidate) > max_chars:
                sub_chunks = _split_on_delimiter(
                    candidate, "\n\n", max_chars
                )
                chunks.extend(sub_chunks[:-1])
                current_chunk = sub_chunks[-1] if sub_chunks else ""
            else:
                current_chunk = candidate

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def _split_on_delimiter(
    text: str, delimiter: str, max_chars: int
) -> list[str]:
    parts = text.split(delimiter)
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) + len(delimiter) <= max_chars:
            current += (delimiter if current else "") + part
        else:
            if current:
                chunks.append(current)
            current = part[:max_chars]
    if current:
        chunks.append(current)
    return chunks
