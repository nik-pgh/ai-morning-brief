from datetime import datetime, timezone

from src.collector import (
    _batch_accounts,
    _parse_tweet_response,
)
from src.models import RawTweet, TweetAuthor


def _make_author(**kw):
    defaults = dict(id="a1", username="user1", name="User 1", followers_count=100)
    defaults.update(kw)
    return TweetAuthor(**defaults)


def _make_tweet(**kw):
    defaults = dict(
        id="t1",
        text="Hello",
        author=_make_author(),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(kw)
    return RawTweet(**defaults)


# --- _batch_accounts tests ---

def test_batch_accounts_single_batch():
    accounts = ["user1", "user2", "user3"]
    batches = _batch_accounts(accounts, max_length=512)
    assert len(batches) == 1
    assert batches[0] == accounts


def test_batch_accounts_splits_on_length():
    accounts = [f"user{i}" for i in range(50)]
    batches = _batch_accounts(accounts, max_length=512)
    assert len(batches) > 1
    all_accounts = [a for batch in batches for a in batch]
    assert all_accounts == accounts


def test_batch_accounts_respects_query_limit():
    accounts = ["karpathy", "OpenAI", "AndrewYNg", "geoffreyhinton", "drfeifei",
                "lexfridman", "ycombinator", "GoogleDeepMind", "jovialjoy", "sama"]
    batches = _batch_accounts(accounts, max_length=512)
    for batch in batches:
        from_clause = " OR ".join([f"from:{a}" for a in batch])
        query = f"({from_clause}) -is:retweet"
        assert len(query) <= 512


def test_batch_accounts_empty():
    batches = _batch_accounts([])
    assert batches == []


# --- _parse_tweet_response tests ---

def test_parse_tweet_response_basic():
    data = {
        "data": [
            {
                "id": "123",
                "text": "Hello world",
                "author_id": "user123",
                "created_at": "2024-01-01T12:00:00.000Z",
                "public_metrics": {
                    "retweet_count": 5,
                    "reply_count": 2,
                    "like_count": 10,
                    "quote_count": 1,
                },
                "entities": {
                    "urls": [{"expanded_url": "https://example.com"}],
                    "hashtags": [{"tag": "AI"}],
                },
            }
        ],
        "includes": {
            "users": [
                {
                    "id": "user123",
                    "username": "testuser",
                    "name": "Test User",
                    "public_metrics": {"followers_count": 1000},
                }
            ]
        },
    }

    result = _parse_tweet_response(data)
    assert len(result) == 1
    tweet = result[0]
    assert tweet.id == "123"
    assert tweet.text == "Hello world"
    assert tweet.author.username == "testuser"
    assert tweet.author.followers_count == 1000
    assert tweet.retweet_count == 5
    assert tweet.like_count == 10
    assert tweet.urls == ["https://example.com"]
    assert tweet.hashtags == ["AI"]


def test_parse_tweet_response_missing_user():
    data = {
        "data": [
            {
                "id": "123",
                "text": "Hello",
                "author_id": "unknown_user",
                "created_at": "2024-01-01T12:00:00.000Z",
            }
        ],
        "includes": {"users": []},
    }

    result = _parse_tweet_response(data)
    assert len(result) == 1
    assert result[0].author.username == "unknown"


def test_parse_tweet_response_empty():
    result = _parse_tweet_response({})
    assert result == []
