from datetime import datetime, timezone

from src.collector import (
    _batch_accounts,
    _extract_keywords,
    _extract_top_authors,
    _merge_tweets,
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


# --- _extract_keywords tests ---

def test_extract_keywords_from_hashtags():
    tweets = [
        _make_tweet(hashtags=["AI", "LLM"]),
        _make_tweet(hashtags=["ai", "GPT"]),
        _make_tweet(hashtags=["LLM"]),
    ]
    result = _extract_keywords(tweets)
    # "llm" appears 2x, "ai" appears 2x, "gpt" appears 1x
    assert result[0] in ("llm", "ai")  # tie between llm and ai
    assert "gpt" in result


def test_extract_keywords_max_20():
    tweets = [_make_tweet(hashtags=[f"tag{i}" for i in range(50)])]
    result = _extract_keywords(tweets)
    assert len(result) <= 20


def test_extract_keywords_empty():
    result = _extract_keywords([])
    assert result == []


# --- _extract_top_authors tests ---

def test_extract_top_authors_sorted_by_followers():
    tweets = [
        _make_tweet(id="t1", author=_make_author(id="a1", followers_count=100)),
        _make_tweet(id="t2", author=_make_author(id="a2", followers_count=1000)),
        _make_tweet(id="t3", author=_make_author(id="a3", followers_count=500)),
    ]
    result = _extract_top_authors(tweets, limit=3)
    follower_counts = [a.followers_count for a in result]
    assert follower_counts == [1000, 500, 100]


def test_extract_top_authors_deduplicates():
    author = _make_author(id="a1")
    tweets = [
        _make_tweet(id="t1", author=author),
        _make_tweet(id="t2", author=author),
    ]
    result = _extract_top_authors(tweets, limit=10)
    assert len(result) == 1


def test_extract_top_authors_respects_limit():
    tweets = [
        _make_tweet(id=f"t{i}", author=_make_author(id=f"a{i}"))
        for i in range(10)
    ]
    result = _extract_top_authors(tweets, limit=3)
    assert len(result) == 3


# --- _batch_accounts tests ---

def test_batch_accounts_single_batch():
    accounts = ["user1", "user2", "user3"]
    batches = _batch_accounts(accounts, max_length=512)
    assert len(batches) == 1
    assert batches[0] == accounts


def test_batch_accounts_splits_on_length():
    # Create enough accounts to exceed 512 chars
    accounts = [f"user{i}" for i in range(50)]
    batches = _batch_accounts(accounts, max_length=512)
    assert len(batches) > 1
    # Verify all accounts are included
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


# --- _merge_tweets tests ---

def test_merge_tweets_no_duplicates():
    tweet1 = _make_tweet(id="t1")
    tweet2 = _make_tweet(id="t2")
    tweet3 = _make_tweet(id="t3")

    account_tweets = [tweet1, tweet2]
    general_tweets = [tweet3]

    result = _merge_tweets(account_tweets, general_tweets)
    assert len(result) == 3
    assert [t.id for t in result] == ["t1", "t2", "t3"]


def test_merge_tweets_deduplicates():
    tweet1 = _make_tweet(id="t1")
    tweet2 = _make_tweet(id="t2")
    tweet1_dup = _make_tweet(id="t1")  # Same id as tweet1

    account_tweets = [tweet1, tweet2]
    general_tweets = [tweet1_dup]

    result = _merge_tweets(account_tweets, general_tweets)
    assert len(result) == 2
    assert [t.id for t in result] == ["t1", "t2"]


def test_merge_tweets_prefers_account_tweets():
    # Account tweet should be kept when there's a duplicate
    account_tweet = _make_tweet(id="t1", text="from account")
    general_tweet = _make_tweet(id="t1", text="from general")

    result = _merge_tweets([account_tweet], [general_tweet])
    assert len(result) == 1
    assert result[0].text == "from account"


def test_merge_tweets_empty():
    result = _merge_tweets([], [])
    assert result == []


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
