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
        influential_accounts=cfg["collector"].get("influential_accounts", []),
        account_fetch_limit=cfg["collector"].get("account_fetch_limit", 100),
        blog_sources=cfg.get("blog_sources", []),
        content_max_chars_blog=cfg["crawler"]["content_limits"]["blog"],
        content_max_chars_paper=cfg["crawler"]["content_limits"]["paper"],
        content_max_chars_readme=cfg["crawler"]["content_limits"]["readme"],
        openai_model=cfg["analyzer"]["openai_model"],
        openai_max_tokens=cfg["analyzer"]["openai_max_tokens"],
        analyzer_batch_size=cfg["analyzer"].get("batch_size", 10),
        discord_max_embed_chars=cfg["delivery"]["discord_max_embed_chars"],
    )
