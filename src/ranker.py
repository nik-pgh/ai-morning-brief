import logging
from collections import Counter

from src.models import (
    CollectorOutput,
    RankerOutput,
    RawTweet,
    ScoredTweet,
    Settings,
    WorkNotebook,
)

logger = logging.getLogger(__name__)

_AI_TERMS = [
    "llm", "gpt", "claude", "gemini", "transformer", "diffusion",
    "fine-tuning", "rag", "agent", "reasoning", "multimodal",
    "open-source", "benchmark", "rlhf", "moe", "vision",
    "embedding", "tokenizer", "inference", "training",
]


def rank(
    collector_output: CollectorOutput,
    settings: Settings,
    notebook: WorkNotebook,
) -> RankerOutput:
    scored = []
    for tweet in collector_output.tweets:
        score = _compute_score(tweet)
        scored.append(ScoredTweet(tweet=tweet, engagement_score=score))

    scored.sort(key=lambda s: s.engagement_score, reverse=True)
    top_tweets = scored[: settings.top_tweets_count]

    trending_keywords = _compact_keywords(
        top_tweets, settings.final_keyword_count
    )

    notebook.trending_keywords = trending_keywords

    logger.info(
        f"Ranked {len(scored)} tweets, kept top {len(top_tweets)}. "
        f"Trending keywords: {trending_keywords}"
    )
    return RankerOutput(
        ranked_tweets=top_tweets,
        trending_keywords=trending_keywords,
    )


def _compute_score(tweet: RawTweet) -> float:
    return (
        tweet.like_count * 1.0
        + tweet.retweet_count * 2.0
        + tweet.reply_count * 1.5
        + tweet.quote_count * 3.0
    )


def _compact_keywords(
    scored_tweets: list[ScoredTweet], limit: int
) -> list[str]:
    counter: Counter[str] = Counter()
    for st in scored_tweets:
        for tag in st.tweet.hashtags:
            counter[tag.lower()] += 1
        text_lower = st.tweet.text.lower()
        for term in _AI_TERMS:
            if term in text_lower:
                counter[term] += 1

    return [kw for kw, _ in counter.most_common(limit)]
