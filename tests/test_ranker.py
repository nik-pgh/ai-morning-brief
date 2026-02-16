from datetime import datetime, timezone

from src.models import (
    CollectorOutput,
    RawTweet,
    Settings,
    TweetAuthor,
    WorkNotebook,
)
from src.ranker import _compact_keywords, _compute_score, rank


def _make_author(**kw):
    defaults = dict(id="a1", username="user1", name="User 1", followers_count=100)
    defaults.update(kw)
    return TweetAuthor(**defaults)


def _make_tweet(**kw):
    defaults = dict(
        id="t1",
        text="Hello world",
        author=_make_author(),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        retweet_count=0,
        reply_count=0,
        like_count=0,
        quote_count=0,
        urls=[],
        hashtags=[],
    )
    defaults.update(kw)
    return RawTweet(**defaults)


def _make_settings(**kw):
    defaults = dict(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://example.com",
        seed_keywords=["LLM"],
        top_tweets_count=50,
        final_keyword_count=10,
    )
    defaults.update(kw)
    return Settings(**defaults)


def _make_notebook():
    return WorkNotebook(run_date=datetime.now(timezone.utc))


# --- _compute_score tests ---

def test_compute_score_zeros():
    tweet = _make_tweet()
    assert _compute_score(tweet) == 0.0


def test_compute_score_weighted():
    tweet = _make_tweet(like_count=10, retweet_count=5, reply_count=4, quote_count=2)
    # 10*1.0 + 5*2.0 + 4*1.5 + 2*3.0 = 10 + 10 + 6 + 6 = 32
    assert _compute_score(tweet) == 32.0


def test_compute_score_quotes_weighted_highest():
    t1 = _make_tweet(quote_count=10)
    t2 = _make_tweet(like_count=10)
    assert _compute_score(t1) > _compute_score(t2)


# --- rank tests ---

def test_rank_sorts_descending():
    tweets = [
        _make_tweet(id="low", like_count=1),
        _make_tweet(id="high", like_count=100),
        _make_tweet(id="mid", like_count=50),
    ]
    collector_output = CollectorOutput(
        tweets=tweets,
        discovered_keywords=[],
        top_authors=[],
        fetched_at=datetime.now(timezone.utc),
    )
    settings = _make_settings(top_tweets_count=3)
    result = rank(collector_output, settings, _make_notebook())

    ids = [st.tweet.id for st in result.ranked_tweets]
    assert ids == ["high", "mid", "low"]


def test_rank_respects_top_tweets_count():
    tweets = [_make_tweet(id=f"t{i}", like_count=i) for i in range(10)]
    collector_output = CollectorOutput(
        tweets=tweets,
        discovered_keywords=[],
        top_authors=[],
        fetched_at=datetime.now(timezone.utc),
    )
    settings = _make_settings(top_tweets_count=3)
    result = rank(collector_output, settings, _make_notebook())
    assert len(result.ranked_tweets) == 3


def test_rank_populates_notebook_trending_keywords():
    tweets = [
        _make_tweet(id="t1", text="LLM is great", hashtags=["AI", "LLM"]),
        _make_tweet(id="t2", text="transformer model", hashtags=["AI"]),
    ]
    collector_output = CollectorOutput(
        tweets=tweets,
        discovered_keywords=[],
        top_authors=[],
        fetched_at=datetime.now(timezone.utc),
    )
    settings = _make_settings(top_tweets_count=50, final_keyword_count=5)
    notebook = _make_notebook()
    rank(collector_output, settings, notebook)
    assert len(notebook.trending_keywords) > 0
    assert "ai" in notebook.trending_keywords


# --- _compact_keywords tests ---

def test_compact_keywords_limits_count():
    from src.models import ScoredTweet

    scored = [
        ScoredTweet(
            tweet=_make_tweet(hashtags=[f"tag{i}" for i in range(20)]),
            engagement_score=1.0,
        )
    ]
    result = _compact_keywords(scored, 5)
    assert len(result) <= 5


def test_compact_keywords_includes_ai_terms_from_text():
    from src.models import ScoredTweet

    scored = [
        ScoredTweet(
            tweet=_make_tweet(text="This is about transformer and rag systems"),
            engagement_score=1.0,
        )
    ]
    result = _compact_keywords(scored, 10)
    assert "transformer" in result
    assert "rag" in result
