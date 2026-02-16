import logging
from datetime import datetime

from src.models import DigestOutput, Settings, SummarizerOutput

logger = logging.getLogger(__name__)


def build_digest(
    summarizer_output: SummarizerOutput,
    settings: Settings,
) -> DigestOutput:
    today = datetime.now().strftime("%B %d, %Y")
    title = f"AI Morning Brief — {today}"

    full_markdown = (
        f"# {title}\n\n"
        f"# Keywords\n{summarizer_output.keywords_section}\n\n"
        f"# Summary\n{summarizer_output.summaries_section}\n\n"
        f"# Connections\n{summarizer_output.connections_section}\n\n"
        f"# Further Reading\n{summarizer_output.further_reading_section}"
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
