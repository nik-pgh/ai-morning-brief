import json
import logging

from openai import OpenAI

from src.models import (
    AnalyzedItem,
    AnalyzerOutput,
    Connection,
    CrawlerOutput,
    Settings,
    WorkNotebook,
)

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM_PROMPT = """\
You are an AI research analyst. For each tweet and its referenced content, provide:
1. category: one of [research, release, benchmark, opinion, tooling]
2. why_it_matters: 1-3 sentences explaining the significance and the "why?" behind this development
3. key_findings: list of 2-4 bullet points of the most important takeaways
4. reference_links: list of URLs that a human should follow for deeper understanding

Think deeply about WHY this matters, not just WHAT it is. Consider implications for the field.

Respond as JSON: {"items": [{"tweet_id": "...", "category": "...", "why_it_matters": "...", "key_findings": [...], "reference_links": [...]}]}"""

CLASSIFY_USER_TEMPLATE = """\
Analyze these {count} AI-related tweets and their referenced content:

{items_json}

For each item, classify it and explain why it matters to the AI community."""

CONNECTIONS_SYSTEM_PROMPT = """\
You are an AI research analyst. Given a list of analyzed AI developments, find meaningful connections between them.

A connection exists when:
- Two items reference the same model, paper, or technique
- One item builds upon or responds to another
- Items share a common theme or trend

Respond as JSON: {"connections": [{"item_ids": ["id1", "id2"], "relationship": "description"}]}"""


def analyze(
    crawler_output: CrawlerOutput,
    settings: Settings,
    notebook: WorkNotebook,
) -> AnalyzerOutput:
    client = OpenAI(api_key=settings.openai_api_key)

    items = _classify_items(client, crawler_output, settings)
    connections = _find_connections(client, items, settings)

    notebook.connection_notes = [c.relationship for c in connections]

    logger.info(
        f"Analyzed {len(items)} items, found {len(connections)} connections"
    )
    return AnalyzerOutput(items=items, connections=connections)


def _classify_items(
    client: OpenAI,
    crawler_output: CrawlerOutput,
    settings: Settings,
) -> list[AnalyzedItem]:
    items_for_llm = []
    for et in crawler_output.enriched_tweets:
        item = {
            "tweet_id": et.scored_tweet.tweet.id,
            "tweet_text": et.scored_tweet.tweet.text,
            "author": et.scored_tweet.tweet.author.username,
            "engagement_score": et.scored_tweet.engagement_score,
            "referenced_content": [
                {
                    "type": c.source_type,
                    "title": c.title,
                    "url": c.source_url,
                    "excerpt": c.content[:500],
                }
                for c in et.crawled_contents
            ],
        }
        items_for_llm.append(item)

    all_analyzed: list[AnalyzedItem] = []
    batch_size = 10

    for i in range(0, len(items_for_llm), batch_size):
        batch = items_for_llm[i : i + batch_size]
        user_msg = CLASSIFY_USER_TEMPLATE.format(
            count=len(batch),
            items_json=json.dumps(batch, indent=2, default=str),
        )

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=settings.openai_max_tokens * 2,
            response_format={"type": "json_object"},
        )

        parsed = json.loads(response.choices[0].message.content)
        result_list = (
            parsed if isinstance(parsed, list) else parsed.get("items", [])
        )

        for r in result_list:
            all_analyzed.append(
                AnalyzedItem(
                    tweet_id=r["tweet_id"],
                    category=r.get("category", "opinion"),
                    why_it_matters=r.get("why_it_matters", ""),
                    key_findings=r.get("key_findings", []),
                    related_tweet_ids=[],
                    reference_links=r.get("reference_links", []),
                )
            )

    return all_analyzed


def _find_connections(
    client: OpenAI,
    items: list[AnalyzedItem],
    settings: Settings,
) -> list[Connection]:
    if len(items) < 2:
        return []

    summaries = [
        {
            "tweet_id": item.tweet_id,
            "category": item.category,
            "why": item.why_it_matters,
            "findings": item.key_findings,
        }
        for item in items
    ]

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": CONNECTIONS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Find connections among these {len(summaries)} items:\n\n"
                    + json.dumps(summaries, indent=2, default=str)
                ),
            },
        ],
        temperature=0.3,
        max_tokens=settings.openai_max_tokens,
        response_format={"type": "json_object"},
    )

    parsed = json.loads(response.choices[0].message.content)
    connections = []
    for c in parsed.get("connections", []):
        conn = Connection(
            item_ids=c["item_ids"],
            relationship=c["relationship"],
        )
        connections.append(conn)
        # Backfill related_tweet_ids
        for item in items:
            if item.tweet_id in c["item_ids"]:
                other_ids = [
                    i for i in c["item_ids"] if i != item.tweet_id
                ]
                item.related_tweet_ids.extend(other_ids)

    return connections
