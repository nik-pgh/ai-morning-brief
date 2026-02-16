import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.models import Settings


def load_settings() -> Settings:
    load_dotenv()

    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    return Settings(
        twitter_bearer_token=os.environ["TWITTER_BEARER_TOKEN"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        discord_webhook_url=os.environ["DISCORD_WEBHOOK_URL"],
        github_token=os.environ.get("GITHUB_TOKEN"),
        seed_keywords=cfg["collector"]["seed_keywords"],
        influential_accounts=cfg["collector"].get("influential_accounts", []),
        account_fetch_limit=cfg["collector"].get("account_fetch_limit", 100),
        tweet_fetch_limit=cfg["collector"]["tweet_fetch_limit"],
        top_tweets_count=cfg["collector"]["top_tweets_count"],
        top_authors_count=cfg["collector"]["top_authors_count"],
        final_keyword_count=cfg["crawler"]["final_keyword_count"],
        arxiv_max_results=cfg["crawler"]["arxiv_max_results"],
        content_max_chars_blog=cfg["crawler"]["content_limits"]["blog"],
        content_max_chars_paper=cfg["crawler"]["content_limits"]["paper"],
        content_max_chars_readme=cfg["crawler"]["content_limits"]["readme"],
        openai_model=cfg["analyzer"]["openai_model"],
        openai_max_tokens=cfg["analyzer"]["openai_max_tokens"],
        discord_max_embed_chars=cfg["delivery"]["discord_max_embed_chars"],
    )
