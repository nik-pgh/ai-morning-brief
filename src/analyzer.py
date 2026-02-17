import json
import logging

from openai import OpenAI

from src.models import (
    AnalyzerOutput,
    ContentItem,
    ContentSummary,
    Insight,
    RelationshipAnalysis,
    Settings,
    WorkNotebook,
)

logger = logging.getLogger(__name__)

# --- Phase 1: Summarize each piece of content ---

SUMMARIZE_SYSTEM_PROMPT = """\
You are an AI research analyst. For each content item, produce a concise summary that captures:
1. The main point or announcement
2. Key technical details or claims
3. All reference links found in the content

Respond as JSON: {"summaries": [{"item_id": "...", "summary": "...", "reference_links": ["..."]}]}"""

SUMMARIZE_USER_TEMPLATE = """\
Summarize these {count} content items. For each, provide a clear summary and list all reference links.

{items_json}"""

# --- Phase 2: Analyze relationships ---

RELATIONSHIPS_SYSTEM_PROMPT = """\
You are an AI research analyst. Given summaries of today's AI-related content from Twitter and blogs, find meaningful relationships between them.

A relationship exists when:
- Two items discuss the same model, paper, technique, or product
- One item builds upon, responds to, or extends another
- Items share a common theme, trend, or concern
- Items represent different perspectives on the same topic

Rate each relationship strength as "strong", "moderate", or "weak".

Respond as JSON: {"relationships": [{"related_item_ids": ["id1", "id2"], "relationship": "description", "strength": "strong|moderate|weak"}]}"""

# --- Phase 3: Derive insights ---

INSIGHTS_SYSTEM_PROMPT = """\
You are an AI intelligence analyst. Given content summaries and their relationships, derive actionable insights.

For each insight:
- Write a clear title
- Write a paragraph that combines and relates information from multiple sources
- Classify the level: "technical" (engineering/research implications), "business" (market/strategy implications), or "product" (product development implications)
- List the source item IDs that inform this insight

Focus on what practitioners, researchers, and decision-makers should pay attention to. Connect the dots across different sources.

Respond as JSON: {"insights": [{"title": "...", "content": "...", "level": "technical|business|product", "source_item_ids": ["..."]}]}"""


def analyze(
    items: list[ContentItem],
    settings: Settings,
    notebook: WorkNotebook,
) -> AnalyzerOutput:
    if not items:
        return AnalyzerOutput(summaries=[], relationships=[], insights=[])

    client = OpenAI(api_key=settings.openai_api_key)

    # Phase 1: Summarize each content item
    summaries = _summarize_items(client, items, settings)
    logger.info(f"Phase 1: Summarized {len(summaries)} items")

    # Phase 2: Analyze relationships
    relationships = _find_relationships(client, summaries, settings)
    logger.info(f"Phase 2: Found {len(relationships)} relationships")

    # Phase 3: Derive insights
    insights = _derive_insights(client, summaries, relationships, settings)
    logger.info(f"Phase 3: Derived {len(insights)} insights")

    return AnalyzerOutput(
        summaries=summaries,
        relationships=relationships,
        insights=insights,
    )


def _summarize_items(
    client: OpenAI,
    items: list[ContentItem],
    settings: Settings,
) -> list[ContentSummary]:
    items_for_llm = []
    for item in items:
        entry = {
            "item_id": item.id,
            "source_type": item.source_type,
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
        items_for_llm.append(entry)

    all_summaries: list[ContentSummary] = []
    batch_size = settings.analyzer_batch_size

    for i in range(0, len(items_for_llm), batch_size):
        batch = items_for_llm[i : i + batch_size]
        user_msg = SUMMARIZE_USER_TEMPLATE.format(
            count=len(batch),
            items_json=json.dumps(batch, indent=2, default=str),
        )

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=settings.openai_max_tokens * 2,
            response_format={"type": "json_object"},
        )

        parsed = json.loads(response.choices[0].message.content)
        for s in parsed.get("summaries", []):
            all_summaries.append(
                ContentSummary(
                    item_id=s["item_id"],
                    summary=s.get("summary", ""),
                    reference_links=s.get("reference_links", []),
                )
            )

    return all_summaries


def _find_relationships(
    client: OpenAI,
    summaries: list[ContentSummary],
    settings: Settings,
) -> list[RelationshipAnalysis]:
    if len(summaries) < 2:
        return []

    summary_data = [
        {
            "item_id": s.item_id,
            "summary": s.summary,
            "reference_links": s.reference_links,
        }
        for s in summaries
    ]

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": RELATIONSHIPS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Find relationships among these {len(summary_data)} content items:\n\n"
                    + json.dumps(summary_data, indent=2, default=str)
                ),
            },
        ],
        temperature=0.3,
        max_tokens=settings.openai_max_tokens,
        response_format={"type": "json_object"},
    )

    parsed = json.loads(response.choices[0].message.content)
    relationships = []
    for r in parsed.get("relationships", []):
        relationships.append(
            RelationshipAnalysis(
                related_item_ids=r["related_item_ids"],
                relationship=r["relationship"],
                strength=r.get("strength", "moderate"),
            )
        )

    return relationships


def _derive_insights(
    client: OpenAI,
    summaries: list[ContentSummary],
    relationships: list[RelationshipAnalysis],
    settings: Settings,
) -> list[Insight]:
    context = {
        "summaries": [
            {"item_id": s.item_id, "summary": s.summary}
            for s in summaries
        ],
        "relationships": [
            {
                "related_item_ids": r.related_item_ids,
                "relationship": r.relationship,
                "strength": r.strength,
            }
            for r in relationships
        ],
    }

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Derive insights from these summaries and their relationships:\n\n"
                    + json.dumps(context, indent=2, default=str)
                ),
            },
        ],
        temperature=0.4,
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
                level=ins.get("level", "technical"),
                source_item_ids=ins.get("source_item_ids", []),
            )
        )

    return insights
