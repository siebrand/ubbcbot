"""The message sender Lambda, bot side: a message per customer, and a failure report to the admin."""

import asyncio
from unittest.mock import Mock, patch

import pytest
import requests

import message_sender

TOKEN = "1234567890:AAH-abcdefghijklmnopqrstuvwxyz_0123"


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
