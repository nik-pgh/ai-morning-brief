from unittest.mock import MagicMock

from src.delivery import deliver, _execute_with_retry
from src.models import DigestOutput, Settings


def _make_settings():
    return Settings(
        twitter_bearer_token="test",
        openai_api_key="test",
        discord_webhook_url="https://discord.com/api/webhooks/test",
    )


def _make_digest(num_chunks=1):
    return DigestOutput(
        title="AI Morning Brief — Test",
        full_markdown="# Test\nContent",
        chunks=["chunk content " * 10] * num_chunks,
    )


def test_deliver_sends_one_embed_per_message(mocker):
    mock_webhook_cls = mocker.patch("src.delivery.DiscordWebhook")
    mock_embed_cls = mocker.patch("src.delivery.DiscordEmbed")

    instances = []

    def make_webhook(**kw):
        inst = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        inst.execute.return_value = mock_response
        instances.append(inst)
        return inst

    mock_webhook_cls.side_effect = make_webhook

    deliver(_make_digest(3), _make_settings())

    # One webhook message per chunk
    assert len(instances) == 3
    for inst in instances:
        inst.add_embed.assert_called_once()
        inst.execute.assert_called_once()


def test_deliver_single_chunk(mocker):
    mock_webhook_cls = mocker.patch("src.delivery.DiscordWebhook")
    mock_embed_cls = mocker.patch("src.delivery.DiscordEmbed")

    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_instance.execute.return_value = mock_response
    mock_webhook_cls.return_value = mock_instance

    deliver(_make_digest(1), _make_settings())

    mock_instance.add_embed.assert_called_once()
    mock_instance.execute.assert_called_once()


def test_execute_with_retry_succeeds_first_try():
    webhook = MagicMock()
    response = MagicMock()
    response.status_code = 200
    webhook.execute.return_value = response

    _execute_with_retry(webhook, max_retries=3)
    webhook.execute.assert_called_once()


def test_execute_with_retry_retries_on_failure(mocker):
    mocker.patch("src.delivery.time.sleep")
    webhook = MagicMock()

    fail_resp = MagicMock()
    fail_resp.status_code = 500
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    webhook.execute.side_effect = [fail_resp, ok_resp]

    _execute_with_retry(webhook, max_retries=3)
    assert webhook.execute.call_count == 2
