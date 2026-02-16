import json
import logging
import re

from openai import OpenAI

from src.models import (
    AnalyzerOutput,
    Settings,
    SummarizerOutput,
    WorkNotebook,
)

logger = logging.getLogger(__name__)

SUMMARIZER_SYSTEM_PROMPT = """\
You are an AI intelligence briefing writer. Create a concise morning brief from the analyzed developments.

Your output MUST have exactly four markdown sections:

# Keywords
List the top trending AI keywords/topics today as a comma-separated list.

# Summary
For each significant development (max 5-7 items), write:
### [Title]
[2-3 sentence summary]
- **Original tweet:** [tweet URL]
- **References:** [list of reference links]

# Connections
Describe how today's developments relate to each other. Use bullet points.

# Further Reading
Suggest 3-5 links for readers who want to go deeper. Annotate each with a one-line description.

IMPORTANT CONSTRAINTS:
- Total output must be under 3500 characters (Discord limit)
- Be concise but informative
- Always include original tweet URLs and reference links
- Focus on the "why" not just the "what"
"""


def summarize(
    analyzer_output: AnalyzerOutput,
    settings: Settings,
    notebook: WorkNotebook,
) -> SummarizerOutput:
    client = OpenAI(api_key=settings.openai_api_key)

    context = {
        "date": notebook.run_date.strftime("%B %d, %Y"),
        "trending_keywords": notebook.trending_keywords,
        "items": [
            {
                "tweet_id": item.tweet_id,
                "tweet_url": f"https://x.com/i/status/{item.tweet_id}",
                "category": item.category,
                "why_it_matters": item.why_it_matters,
                "key_findings": item.key_findings,
                "reference_links": item.reference_links,
            }
            for item in analyzer_output.items
        ],
        "connections": [
            {"ids": c.item_ids, "relationship": c.relationship}
            for c in analyzer_output.connections
        ],
    }

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Generate the AI Morning Brief for {context['date']}.\n\n"
                    + json.dumps(context, indent=2, default=str)
                ),
            },
        ],
        temperature=0.4,
        max_tokens=2048,
    )

    full_text = response.choices[0].message.content
    sections = _parse_sections(full_text)

    logger.info(f"Summary generated: {len(full_text)} chars")
    return SummarizerOutput(
        keywords_section=sections.get("keywords", ""),
        summaries_section=sections.get("summary", ""),
        connections_section=sections.get("connections", ""),
        further_reading_section=sections.get("further reading", ""),
    )


def _parse_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in markdown.split("\n"):
        heading_match = re.match(r"^#\s+(.+)$", line)
        if heading_match:
            if current_name:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = heading_match.group(1).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_name:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections
