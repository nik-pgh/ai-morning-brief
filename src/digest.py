import logging
from datetime import datetime

from src.models import AnalyzerOutput, DigestOutput, Settings

logger = logging.getLogger(__name__)


def build_digest(
    analyzer_output: AnalyzerOutput,
    settings: Settings,
) -> DigestOutput:
    today = datetime.now().strftime("%B %d, %Y")
    title = f"AI Morning Brief — {today}"

    # Build Summary section
    summary_lines = []
    for s in analyzer_output.summaries:
        summary_lines.append(f"### {s.item_id}")
        summary_lines.append(s.summary)
        if s.reference_links:
            summary_lines.append("**References:** " + ", ".join(s.reference_links))
        summary_lines.append("")

    # Build Analysis section
    analysis_lines = []
    for r in analyzer_output.relationships:
        strength_tag = f"[{r.strength}]" if r.strength else ""
        items = ", ".join(r.related_item_ids)
        analysis_lines.append(f"- {strength_tag} **{items}**: {r.relationship}")

    # Build Insights section
    insight_lines = []
    for ins in analyzer_output.insights:
        level_tag = f"[{ins.level.upper()}]"
        insight_lines.append(f"### {level_tag} {ins.title}")
        insight_lines.append(ins.content)
        insight_lines.append("")

    full_markdown = (
        f"# {title}\n\n"
        f"# Summary\n{chr(10).join(summary_lines)}\n\n"
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
