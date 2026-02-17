import os
from unittest.mock import patch

from src.config import load_settings


def test_load_settings_from_env_and_yaml():
    env = {
        "TWITTER_BEARER_TOKEN": "twt-test",
        "OPENAI_API_KEY": "oai-test",
        "DISCORD_WEBHOOK_URL": "https://discord.test/webhook",
        "GITHUB_TOKEN": "gh-test",
    }
    with patch.dict(os.environ, env, clear=False):
        settings = load_settings()

    assert settings.twitter_bearer_token == "twt-test"
    assert settings.openai_api_key == "oai-test"
    assert settings.discord_webhook_url == "https://discord.test/webhook"
    assert settings.github_token == "gh-test"
    assert len(settings.influential_accounts) > 0
    assert len(settings.blog_sources) > 0
    assert settings.account_fetch_limit == 100


def test_load_settings_github_token_optional():
    env = {
        "TWITTER_BEARER_TOKEN": "twt-test",
        "OPENAI_API_KEY": "oai-test",
        "DISCORD_WEBHOOK_URL": "https://discord.test/webhook",
    }
    cleaned = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
    cleaned.update(env)
    with patch.dict(os.environ, cleaned, clear=True), \
         patch("src.config.load_dotenv"):
        settings = load_settings()

    assert settings.github_token is None
