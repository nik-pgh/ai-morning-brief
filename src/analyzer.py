import json
import logging

from openai import OpenAI

from src.models import (
    AnalyzerOutput,
    ContentItem,
    ContentSummary,
    Insight,
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
from Twitter and blogs.

Read everything together and extract:
1. **Discussion points**: What are people actively debating or discussing today?
2. **Trends**: What patterns or directions are emerging across multiple sources?
3. **Food for thought**: What surprising, contrarian, or thought-provoking ideas surfaced?

Do NOT compare items one-to-one. Instead, synthesize the overall landscape and \
pull out the most interesting threads.

Respond as JSON: {"discussion_points": ["..."], "trends": ["..."], "food_for_thought": ["..."]}"""

# --- Phase 3: Insights with character ---

INSIGHTS_SYSTEM_PROMPT = """\
You are a witty, well-read AI analyst who explains complex tech in a friendly, casual way. \
Think of yourself as that one friend who reads everything and explains it over coffee — \
sharp observations, clear language, zero jargon-for-jargon's-sake.

Given today's content summaries and semantic analysis (discussion points, trends, \
food for thought), derive actionable insights that practitioners, researchers, \
and decision-makers should care about.

For each insight:
- Write a catchy, clear title
- Write a paragraph that synthesizes information from multiple sources
- Keep it accessible — if your non-technical friend couldn't follow it, simplify
- Be opinionated where warranted, but fair

Respond as JSON: {"insights": [{"title": "...", "content": "...", "source_item_ids": ["..."]}]}"""


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

    # Phase 3: Derive witty insights
    insights = _derive_insights(client, summaries, semantic, items, settings)
    logger.info(f"Phase 3: Derived {len(insights)} insights")

    return AnalyzerOutput(
        summaries=summaries,
        semantic_analysis=semantic,
        insights=insights,
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
            content_for_analysis.append({
                "type": "tweet",
                "author": item.author,
                "text": item.content,
            })
        else:
            content_for_analysis.append({
                "type": "blog",
                "author": item.author,
                "title": item.title,
                "summary": summary_map.get(item.id, item.content[:500]),
            })

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
    return SemanticAnalysis(
        discussion_points=parsed.get("discussion_points", []),
        trends=parsed.get("trends", []),
        food_for_thought=parsed.get("food_for_thought", []),
    )


def _derive_insights(
    client: OpenAI,
    summaries: list[ContentSummary],
    semantic: SemanticAnalysis,
    items: list[ContentItem],
    settings: Settings,
) -> list[Insight]:
    """Derive witty, accessible insights from all content."""
    context = {
        "blog_summaries": [
            {"item_id": s.item_id, "summary": s.summary} for s in summaries
        ],
        "tweets": [
            {"author": item.author, "text": item.content}
            for item in items
            if item.source_type == "twitter"
        ],
        "discussion_points": semantic.discussion_points,
        "trends": semantic.trends,
        "food_for_thought": semantic.food_for_thought,
    }

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Derive insights from today's AI landscape:\n\n"
                    + json.dumps(context, indent=2, default=str)
                ),
            },
        ],
        temperature=0.5,
        max_tokens=settings.openai_max_tokens * 2,
        response_format={"type": "json_object"},
    )

    parsed = json.loads(response.choices[0].message.content)
    insights = []
    for ins in parsed.get("insights", []):
        insights.append(
            Insight(
                title=ins["title"],
                content=ins["content"],
                source_item_ids=ins.get("source_item_ids", []),
            )
        )

    return insights
