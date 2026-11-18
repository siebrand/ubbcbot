"""The Bot API calls the callback handler makes itself: answering the tap, removing or deleting the keyboard."""

from unittest.mock import Mock, patch

import pytest

from services.callback_handler import CallbackHandler


@pytest.fixture
def post():
    response = Mock(status_code=200, text="")
    response.json.return_value = {"ok": True, "result": True}
    with patch("services.telegram_client.requests.post", return_value=response) as post:
        yield post


@pytest.fixture
def callbacks():
    return CallbackHandler(Mock(), 1, "prod", "token", handlers={}, media_handler=Mock())


def call(post) -> tuple[str, dict]:
    return post.call_args.args[0].rsplit("/", 1)[1], post.call_args.kwargs["json"]


def test_answer_the_tap(post, callbacks):
    assert callbacks._answer_callback_query("q1") is True
    assert call(post) == ("answerCallbackQuery", {"callback_query_id": "q1"})


def test_answer_the_tap_with_a_toast(post, callbacks):
    callbacks._answer_callback_query("q1", text="Kijk in je privéchat")

    assert call(post) == ("answerCallbackQuery", {"callback_query_id": "q1", "text": "Kijk in je privéchat"})


def test_remove_the_keyboard(post, callbacks):
    assert callbacks._edit_message_remove_keyboard(5, 9) is True
    assert call(post) == (
        "editMessageReplyMarkup",
        {"chat_id": 5, "message_id": 9, "reply_markup": {"inline_keyboard": []}},
    )


def test_delete_the_message(post, callbacks):
    assert callbacks._delete_message(5, 9) is True
    assert call(post) == ("deleteMessage", {"chat_id": 5, "message_id": 9})


def test_a_failed_call_is_false(post, callbacks):
    post.return_value = Mock(status_code=400, text="Bad Request: query is too old")

    assert callbacks._answer_callback_query("q1") is False
