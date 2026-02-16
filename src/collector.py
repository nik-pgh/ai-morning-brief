import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

from src.models import (
    CollectorOutput,
    RawTweet,
    Settings,
    TweetAuthor,
    WorkNotebook,
)

logger = logging.getLogger(__name__)

TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
TWEET_FIELDS = "created_at,public_metrics,entities"
USER_FIELDS = "id,username,name,public_metrics"
EXPANSIONS = "author_id"

# Twitter API v2 has a 512 character query limit
MAX_QUERY_LENGTH = 512


def collect(settings: Settings, notebook: WorkNotebook) -> CollectorOutput:
    """
    Phase 1: Fetch tweets from influential accounts.
    Phase 2: Extract keywords from account tweets.
    Phase 3: Combine seed keywords + account-derived keywords.
    Phase 4: Fetch general tweets using combined keywords.
    Phase 5: Merge all tweets (deduplicate).
    Phase 6: Extract final discovered keywords from all tweets.
    """
    # Step 1: Fetch tweets from influential accounts
    account_tweets = _fetch_account_tweets(settings)
    logger.info(f"Fetched {len(account_tweets)} tweets from influential accounts")

    # Step 2: Extract keywords from account tweets
    account_keywords = _extract_keywords(account_tweets)
    logger.info(f"Extracted {len(account_keywords)} keywords from influential accounts")

    # Step 3: Combine seed keywords + account-derived keywords
    combined_keywords = list(settings.seed_keywords)
    for kw in account_keywords:
        if kw.lower() not in [k.lower() for k in combined_keywords]:
            combined_keywords.append(kw)
    combined_keywords = combined_keywords[:15]  # Limit to avoid huge queries

    # Step 4: Fetch general tweets using combined keywords
    general_tweets = _fetch_tweets_with_keywords(settings, combined_keywords)
    logger.info(f"Fetched {len(general_tweets)} tweets from keyword search")

    # Step 5: Merge and deduplicate
    all_tweets = _merge_tweets(account_tweets, general_tweets)
    logger.info(
        f"Merged {len(account_tweets)} account tweets + "
        f"{len(general_tweets)} general tweets = {len(all_tweets)} unique tweets"
    )

    # Step 6: Extract final keywords from all tweets
    discovered_keywords = _extract_keywords(all_tweets)
    top_authors = _extract_top_authors(all_tweets, settings.top_authors_count)

    # Update notebook
    notebook.discovered_keywords = discovered_keywords
    notebook.account_keywords = account_keywords
    notebook.top_author_usernames = [a.username for a in top_authors]

    return CollectorOutput(
        tweets=all_tweets,
        discovered_keywords=discovered_keywords,
        account_keywords=account_keywords,
        top_authors=top_authors,
        fetched_at=datetime.now(timezone.utc),
    )


def _batch_accounts(accounts: list[str], max_length: int = MAX_QUERY_LENGTH) -> list[list[str]]:
    """Split accounts into batches that fit within Twitter query length limit."""
    batches: list[list[str]] = []
    current_batch: list[str] = []
    # Base query overhead: "(from:x OR from:y) -is:retweet" ~ 15 chars overhead
    base_overhead = 20

    for account in accounts:
        # Each account adds "from:username OR " = len(username) + 10 chars
        account_clause = f"from:{account}"

        # Calculate current query length
        if current_batch:
            current_query = " OR ".join([f"from:{a}" for a in current_batch + [account]])
            query_length = len(f"({current_query}) -is:retweet")
        else:
            query_length = len(f"(from:{account}) -is:retweet")

        if query_length > max_length and current_batch:
            batches.append(current_batch)
            current_batch = [account]
        else:
            current_batch.append(account)

    if current_batch:
        batches.append(current_batch)

    return batches


def _parse_tweet_response(data: dict) -> list[RawTweet]:
    """Parse Twitter API response data into RawTweet objects."""
    tweets: list[RawTweet] = []

    users_map = {}
    for user in data.get("includes", {}).get("users", []):
        users_map[user["id"]] = TweetAuthor(
            id=user["id"],
            username=user["username"],
            name=user["name"],
            followers_count=user.get("public_metrics", {}).get("followers_count", 0),
        )

    for tweet_data in data.get("data", []):
        metrics = tweet_data.get("public_metrics", {})
        entities = tweet_data.get("entities", {})

        urls = [
            u["expanded_url"]
            for u in entities.get("urls", [])
            if "expanded_url" in u
        ]
        hashtags = [h["tag"] for h in entities.get("hashtags", [])]

        author = users_map.get(
            tweet_data["author_id"],
            TweetAuthor(
                id=tweet_data["author_id"],
                username="unknown",
                name="Unknown",
            ),
        )

        tweets.append(
            RawTweet(
                id=tweet_data["id"],
                text=tweet_data["text"],
                author=author,
                created_at=tweet_data["created_at"],
                retweet_count=metrics.get("retweet_count", 0),
                reply_count=metrics.get("reply_count", 0),
                like_count=metrics.get("like_count", 0),
                quote_count=metrics.get("quote_count", 0),
                urls=urls,
                hashtags=hashtags,
            )
        )

    return tweets


def _fetch_account_tweets(settings: Settings) -> list[RawTweet]:
    """Fetch tweets from influential accounts in batches."""
    if not settings.influential_accounts:
        return []

    batches = _batch_accounts(settings.influential_accounts)
    logger.info(f"Split {len(settings.influential_accounts)} accounts into {len(batches)} batches")

    headers = {"Authorization": f"Bearer {settings.twitter_bearer_token}"}
    start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    all_tweets: list[RawTweet] = []

    for batch_idx, batch in enumerate(batches):
        from_clause = " OR ".join([f"from:{account}" for account in batch])
        query = f"({from_clause}) -is:retweet"

        logger.debug(f"Batch {batch_idx + 1}/{len(batches)}: query length {len(query)}, accounts: {batch}")

        params = {
            "query": query,
            "max_results": min(100, settings.account_fetch_limit),
            "start_time": start_time,
            "sort_order": "recency",
            "tweet.fields": TWEET_FIELDS,
            "user.fields": USER_FIELDS,
            "expansions": EXPANSIONS,
        }

        pagination_token = None
        batch_tweets: list[RawTweet] = []

        while len(batch_tweets) < settings.account_fetch_limit:
            if pagination_token:
                params["pagination_token"] = pagination_token

            try:
                resp = requests.get(
                    TWITTER_SEARCH_URL, headers=headers, params=params, timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                logger.warning(f"Failed to fetch batch {batch_idx + 1}: {e}")
                break

            batch_tweets.extend(_parse_tweet_response(data))

            pagination_token = data.get("meta", {}).get("next_token")
            if not pagination_token:
                break

        all_tweets.extend(batch_tweets)

    return all_tweets


def _fetch_tweets_with_keywords(
    settings: Settings, keywords: list[str]
) -> list[RawTweet]:
    """Fetch tweets matching the given keywords."""
    keyword_clause = " OR ".join(keywords[:10])
    query = f"({keyword_clause}) -is:retweet lang:en"

    headers = {"Authorization": f"Bearer {settings.twitter_bearer_token}"}
    params = {
        "query": query,
        "max_results": min(100, settings.tweet_fetch_limit),
        "start_time": (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "sort_order": "relevancy",
        "tweet.fields": TWEET_FIELDS,
        "user.fields": USER_FIELDS,
        "expansions": EXPANSIONS,
    }

    all_tweets: list[RawTweet] = []
    pagination_token = None

    while len(all_tweets) < settings.tweet_fetch_limit:
        if pagination_token:
            params["pagination_token"] = pagination_token

        resp = requests.get(
            TWITTER_SEARCH_URL, headers=headers, params=params, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        all_tweets.extend(_parse_tweet_response(data))

        pagination_token = data.get("meta", {}).get("next_token")
        if not pagination_token:
            break

    return all_tweets


def _merge_tweets(
    account_tweets: list[RawTweet], general_tweets: list[RawTweet]
) -> list[RawTweet]:
    """Merge and deduplicate tweets, preferring account tweets."""
    seen_ids: set[str] = set()
    merged: list[RawTweet] = []

    # Add account tweets first (they have priority)
    for tweet in account_tweets:
        if tweet.id not in seen_ids:
            seen_ids.add(tweet.id)
            merged.append(tweet)

    # Add general tweets that weren't already included
    for tweet in general_tweets:
        if tweet.id not in seen_ids:
            seen_ids.add(tweet.id)
            merged.append(tweet)

    return merged


def _extract_keywords(tweets: list[RawTweet]) -> list[str]:
    """Extract hashtags as keywords from tweets."""
    counter: Counter[str] = Counter()
    for tweet in tweets:
        for tag in tweet.hashtags:
            counter[tag.lower()] += 1
    return [tag for tag, _ in counter.most_common(20)]


def _extract_top_authors(tweets: list[RawTweet], limit: int) -> list[TweetAuthor]:
    """Extract top authors by follower count."""
    seen: dict[str, TweetAuthor] = {}
    for tweet in tweets:
        if tweet.author.id not in seen:
            seen[tweet.author.id] = tweet.author
    authors = sorted(seen.values(), key=lambda a: a.followers_count, reverse=True)
    return authors[:limit]
