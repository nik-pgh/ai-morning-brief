import logging
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
    """Fetch recent tweets from listed influential accounts (last 24h)."""
    tweets = _fetch_account_tweets(settings)
    logger.info(f"Collected {len(tweets)} tweets from influential accounts")

    return CollectorOutput(
        tweets=tweets,
        fetched_at=datetime.now(timezone.utc),
    )


def _batch_accounts(accounts: list[str], max_length: int = MAX_QUERY_LENGTH) -> list[list[str]]:
    """Split accounts into batches that fit within Twitter query length limit."""
    batches: list[list[str]] = []
    current_batch: list[str] = []

    for account in accounts:
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
