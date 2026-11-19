"""The message sender Lambda, bot side: a message per customer, and a failure report to the admin."""

import asyncio
from unittest.mock import Mock, patch

import pytest
import requests
from conftest import FAKE_TOKEN

import message_sender

TOKEN = FAKE_TOKEN


def answer(status=200, text=""):
    response = Mock(status_code=status, text=text)
    response.json.return_value = {"ok": status == 200, "result": {"message_id": 1}}
    return response


@pytest.fixture
def post():
    with patch("services.telegram_client.requests.post", return_value=answer()) as post:
        yield post


def send(msg, environment="prod"):
    return asyncio.run(message_sender.send_from_bot(msg, environment, TOKEN))


class TestSendFromBot:
    def test_sends_the_message_with_its_options(self, post):
        result = send(
            {"user_id": 42, "message": "Je bier is er", "parse_mode": "HTML", "disable_web_page_preview": True}
        )

        assert result == {"success": True, "user_id": 42}
        assert post.call_args.args[0].endswith("/sendMessage")
        assert post.call_args.kwargs["json"] == {
            "chat_id": 42,
            "text": "Je bier is er",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

    def test_the_test_environment_marks_the_message(self, post):
        send({"user_id": 42, "message": "hoi"}, environment="test")

        assert post.call_args.kwargs["json"]["text"] == "TEST - hoi"

    def test_a_refused_message_reports_telegrams_answer(self, post):
        post.return_value = answer(403, text='{"description":"Forbidden: bot was blocked by the user"}')

        result = send({"user_id": 42, "message": "hoi", "customer_name": "Jan J"})

        assert result["success"] is False
        assert "blocked by the user" in result["error"]
        assert result["customer_name"] == "Jan J"

    def test_a_network_error_never_puts_the_token_in_the_report(self, post):
        post.side_effect = requests.ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/sendMessage")

        result = send({"user_id": 42, "message": "hoi"})

        assert result["success"] is False
        assert TOKEN not in result["error"]

    def test_a_malformed_message_is_a_failure(self, post):
        result = send({"message": "no user"})

        assert result == {"success": False, "user_id": None, "error": "KeyError", "customer_name": None}
        post.assert_not_called()


@pytest.fixture
def pauses(monkeypatch):
    """The pauses of the Lambda, recorded instead of waited for"""
    recorded = []

    async def pause(seconds):
        recorded.append(seconds)

    monkeypatch.setattr(message_sender, "_pause", pause)
    return recorded


class TestRateLimit:
    def test_bot_messages_go_out_in_batches_with_a_pause_between(self, pauses, monkeypatch):
        in_flight, most = 0, 0

        async def fake_send(msg, environment, bot_token):
            nonlocal in_flight, most
            in_flight += 1
            most = max(most, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return {"success": True, "user_id": msg["user_id"]}

        monkeypatch.setattr(message_sender, "send_from_bot", fake_send)
        messages = [{"user_id": n, "message": "Je bier is er"} for n in range(1, 61)]

        results = asyncio.run(message_sender.send_messages(messages, "prod", TOKEN))

        assert [r["user_id"] for r in results] == list(range(1, 61))
        assert most <= message_sender.BOT_BATCH_SIZE
        assert len(pauses) == 2  # between the three batches of at most 25

    def test_a_429_is_retried_after_the_time_telegram_asks(self, post, pauses):
        too_many = '{"ok":false,"error_code":429,"description":"Too Many Requests","parameters":{"retry_after":3}}'
        post.side_effect = [answer(429, text=too_many), answer()]

        result = send({"user_id": 42, "message": "hoi"})

        assert result == {"success": True, "user_id": 42}
        assert post.call_count == 2
        assert pauses == [3]

    def test_a_message_that_stays_refused_is_reported_after_a_few_tries(self, post, pauses):
        post.return_value = answer(429, text='{"ok":false,"parameters":{"retry_after":1}}')

        result = send({"user_id": 42, "message": "hoi"})

        assert result["success"] is False
        assert post.call_count == message_sender.BOT_SEND_ATTEMPTS


class TestFailureReport:
    def test_the_admin_gets_one_message_listing_the_failures(self, post, monkeypatch):
        monkeypatch.setenv("ADMIN_USER_ID", "777")
        failures = [
            {"user_id": 42, "customer_name": "Jan J", "error": "Forbidden: bot was blocked by the user"},
            {"user_id": 43, "error": "x" * 300},
        ]

        asyncio.run(message_sender.notify_admin_of_failures(failures, "test", TOKEN))

        payload = post.call_args.kwargs["json"]
        assert payload["chat_id"] == 777
        assert payload["text"].startswith("TEST - ⚠️")
        assert "Jan J (ID: 42)" in payload["text"]
        assert "Unknown (ID: 43)" in payload["text"]
        assert "x" * 101 not in payload["text"]  # errors are cut at 100 characters
