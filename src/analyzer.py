import json
import logging

from openai import OpenAI

from src.models import (
    AnalyzerOutput,
    AttributedPoint,
    ContentItem,
    ContentSummary,
    SemanticAnalysis,
    Settings,
    WorkNotebook,
)

logger = logging.getLogger(__name__)

# --- Phase 1: Summarize blog posts (one call per post, skip tweets) ---

BLOG_SUMMARIZE_SYSTEM_PROMPT = """\
You are an AI research analyst. Summarize this blog post concisely, capturing:
1. The main point or announcement
2. Key technical details or claims
3. All reference links found in the content

Respond as JSON: {"item_id": "...", "summary": "...", "reference_links": ["..."]}"""

# --- Phase 2: Holistic semantic analysis ---

SEMANTIC_ANALYSIS_SYSTEM_PROMPT = """\
You are an AI research analyst. You are given all of today's AI-related content \
from Twitter and blogs. Every entry (tweet or blog) has an item_id field.

Read everything together and extract:
1. **Discussion points**: What are people actively debating or discussing today?
2. **Trends**: What patterns or directions are emerging across multiple sources?
3. **Food for thought**: What surprising, contrarian, or thought-provoking ideas surfaced?

Do NOT compare items one-to-one. Instead, synthesize the overall landscape and \
pull out the most interesting threads.

For each point, include source_ids: a list of item_ids (tweets or blogs) whose content \
directly supports that point.

Respond as JSON:
{
  "discussion_points": [{"point": "...", "source_ids": ["tweet_item_id", "blog_item_id"]}],
  "trends":            [{"point": "...", "source_ids": ["tweet_item_id"]}],
  "food_for_thought":  [{"point": "...", "source_ids": []}]
}"""

# --- Phase 3: Creative narrative ---

NARRATIVE_SYSTEM_PROMPT = """\
You are a sharp, opinionated AI journalist writing the morning briefing for AI practitioners, \
researchers, and founders — people who are deeply in the field and have limited time.

INPUT:
- tweets: each has author, url, text
- blog_summaries: each has title, author, url, summary
- discussion_points / trends / food_for_thought: synthesized themes with source_urls

TASK: write a single cohesive narrative piece that weaves everything together critically \
and creatively.

INLINE LINKS — two simple rules:
1. Whenever you reference a tweet or its author, link the relevant phrase to that tweet's url. \
   Example: "[Karpathy called it](https://x.com/karpathy/status/123)"
2. Whenever you reference a blog post or its argument, link the relevant phrase to that blog's url. \
   Example: "[a deep dive on scaling](https://example.com/post)"
Every blog url MUST appear at least once. Tweet urls should appear when that tweet is referenced.

STYLE:
- Synthesize into a unified story — do NOT list or summarize items in isolation.
- Find the real tension, contradiction, or implication hiding across the sources.
- Be opinionated. Have a take. Challenge assumptions where warranted.
- Flowing prose only — no headers, no bullet points, no section labels.
- Voice: brilliant friend who read everything so you don't have to. Sharp, direct, \
  slightly irreverent. Zero filler.
- Hard limit: stay under 3400 characters total.
- End with a punchy line that leaves the reader thinking.

Return only the narrative text. Nothing else."""


def analyze(
    items: list[ContentItem],
    settings: Settings,
    notebook: WorkNotebook,
) -> AnalyzerOutput:
    if not items:
        return AnalyzerOutput(
            summaries=[],
            semantic_analysis=SemanticAnalysis(),
            insights=[],
        )

    client = OpenAI(api_key=settings.openai_api_key)

    # Phase 1: Summarize blog posts only (one call per post)
    summaries = _summarize_blog_posts(client, items, settings)
    logger.info(f"Phase 1: Summarized {len(summaries)} blog posts")

    # Phase 2: Holistic semantic analysis of everything
    semantic = _semantic_analysis(client, items, summaries, settings)
    logger.info(
        f"Phase 2: Found {len(semantic.discussion_points)} discussion points, "
        f"{len(semantic.trends)} trends, "
        f"{len(semantic.food_for_thought)} food-for-thought items"
    )

    # Phase 3: Write creative narrative
    narrative = _write_narrative(client, summaries, semantic, items, settings)
    logger.info(f"Phase 3: Narrative written ({len(narrative)} chars)")

    return AnalyzerOutput(
        summaries=summaries,
        semantic_analysis=semantic,
        narrative=narrative,
    )


def _summarize_blog_posts(
    client: OpenAI,
    items: list[ContentItem],
    settings: Settings,
) -> list[ContentSummary]:
    """Summarize only blog posts, one LLM call per post. Tweets are skipped."""
    blog_items = [item for item in items if item.source_type == "blog"]
    summaries: list[ContentSummary] = []

    for item in blog_items:
        entry = {
            "item_id": item.id,
            "title": item.title,
            "content": item.content[:800],
            "author": item.author,
            "url": item.url,
            "reference_links": item.reference_links,
            "crawled_references": [
                {
                    "type": ref.source_type,
                    "title": ref.title,
                    "url": ref.source_url,
                    "excerpt": ref.content[:500],
                }
                for ref in item.crawled_references
            ],
        }

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": BLOG_SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(entry, indent=2, default=str)},
            ],
            temperature=0.3,
            max_tokens=settings.openai_max_tokens,
            response_format={"type": "json_object"},
        )

        parsed = json.loads(response.choices[0].message.content)
        summaries.append(
            ContentSummary(
                item_id=parsed.get("item_id", item.id),
                summary=parsed.get("summary", ""),
                reference_links=parsed.get("reference_links", []),
            )
        )

    return summaries


def _semantic_analysis(
    client: OpenAI,
    items: list[ContentItem],
    summaries: list[ContentSummary],
    settings: Settings,
) -> SemanticAnalysis:
    """Holistic analysis of all content together."""
    summary_map = {s.item_id: s.summary for s in summaries}

    content_for_analysis = []
    for item in items:
        if item.source_type == "twitter":
            content_for_analysis.append(
                {
                    "type": "tweet",
                    "item_id": item.id,
                    "author": item.author,
                    "text": item.content,
                }
            )
        else:
            content_for_analysis.append(
                {
                    "type": "blog",
                    "item_id": item.id,
                    "author": item.author,
                    "title": item.title,
                    "summary": summary_map.get(item.id, item.content[:500]),
                }
            )

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SEMANTIC_ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(content_for_analysis, indent=2, default=str),
            },
        ],
        temperature=0.4,
        max_tokens=settings.openai_max_tokens * 2,
        response_format={"type": "json_object"},
    )

    parsed = json.loads(response.choices[0].message.content)

    def _to_attributed(raw: list) -> list[AttributedPoint]:
        points = []
        for item in raw:
            if isinstance(item, dict):
                points.append(
                    AttributedPoint(
                        point=item.get("point", ""),
                        source_ids=item.get("source_ids", []),
                    )
                )
            else:
                points.append(AttributedPoint(point=str(item)))
        return points

    return SemanticAnalysis(
        discussion_points=_to_attributed(parsed.get("discussion_points", [])),
        trends=_to_attributed(parsed.get("trends", [])),
        food_for_thought=_to_attributed(parsed.get("food_for_thought", [])),
    )


def _write_narrative(
    client: OpenAI,
    summaries: list[ContentSummary],
    semantic: SemanticAnalysis,
    items: list[ContentItem],
    settings: Settings,
) -> str:
    """Write a single creative narrative synthesizing all content."""
    summary_map = {s.item_id: s.summary for s in summaries}
    item_url_map = {item.id: item.url for item in items}

    def _resolve(points) -> list[dict]:
        return [
            {
                "point": p.point,
                "source_urls": [
                    item_url_map[sid] for sid in p.source_ids if sid in item_url_map
                ],
            }
            for p in points
        ]

    context = {
        "tweets": [
            {"author": item.author, "url": item.url, "text": item.content}
            for item in items
            if item.source_type == "twitter"
        ],
        "blog_summaries": [
            {
                "title": item.title,
                "author": item.author,
                "url": item.url,
                "summary": summary_map.get(item.id, item.content[:500]),
            }
            for item in items
            if item.source_type == "blog"
        ],
        "discussion_points": _resolve(semantic.discussion_points),
        "trends": _resolve(semantic.trends),
        "food_for_thought": _resolve(semantic.food_for_thought),
    }

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": NARRATIVE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Write today's AI briefing narrative:\n\n"
                    + json.dumps(context, indent=2, default=str)
                ),
            },
        ],
        temperature=0.7,
        max_tokens=1000,
    )

    return response.choices[0].message.content.strip()
