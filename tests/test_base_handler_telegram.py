"""What BaseHandler sends to Telegram, and to whom: guests are skipped, group chats in production only get
messages meant for the group, and everything sent in the test environment is marked TEST."""

import logging
from unittest.mock import Mock, patch

import pytest

from handlers.base_handler import BaseHandler

GROUP = -100123
USER = 42
GUEST = -1


def answer(status=200, result=None, text=""):
    response = Mock(status_code=status, text=text)
    response.json.return_value = {"ok": status == 200, "result": result if result is not None else {"message_id": 5}}
    return response


@pytest.fixture
def post():
    with patch("services.telegram_client.requests.post", return_value=answer()) as post:
        yield post


def handler(environment="prod", token="token"):
    return BaseHandler(Mock(), 1, environment, token)


def sent(post) -> dict:
    return post.call_args.kwargs["json"]


def method(post) -> str:
    return post.call_args.args[0].rsplit("/", 1)[1]


class TestSendMessage:
    def test_sends_the_text_with_options(self, post):
        result = handler()._send_message(USER, "hoi", parse_mode="HTML", reply_markup={"inline_keyboard": [[]]})

        assert result == {"success": True, "message_id": 5}
        assert method(post) == "sendMessage"
        assert sent(post) == {
            "chat_id": USER,
            "text": "hoi",
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": [[]]},
        }

    def test_the_test_environment_marks_the_text(self, post):
        handler("test")._send_message(USER, "hoi")

        assert sent(post)["text"] == "TEST - hoi"

    def test_guests_have_no_telegram(self, post):
        assert handler()._send_message(GUEST, "hoi") == {"success": False, "skipped_guest": True}
        post.assert_not_called()

    def test_production_does_not_post_to_a_group_unless_forced(self, post):
        assert handler()._send_message(GROUP, "hoi") == {"success": False}
        post.assert_not_called()

        assert handler()._send_message(GROUP, "hoi", force_group=True)["success"] is True

    def test_the_test_environment_posts_to_groups(self, post):
        assert handler("test")._send_message(GROUP, "hoi")["success"] is True

    def test_a_refused_message(self, post):
        post.return_value = answer(400, text="Bad Request")

        assert handler()._send_message(USER, "hoi") == {"success": False}

    def test_without_a_token(self, post):
        assert handler(token="")._send_message(USER, "hoi") == {"success": False}
        post.assert_not_called()


class TestPhotos:
    def test_a_photo_with_a_caption(self, post):
        assert handler("test")._send_photo(USER, "https://x/a.jpg", caption="Pils") == {
            "success": True,
            "message_id": 5,
        }

        assert method(post) == "sendPhoto"
        assert sent(post) == {"chat_id": USER, "photo": "https://x/a.jpg", "caption": "TEST - Pils"}

    def test_a_presigned_url_is_not_logged(self, post, caplog):
        url = "https://bucket.s3.amazonaws.com/offers/3/a.jpg?X-Amz-Signature=secret123&X-Amz-Expires=3600"

        with caplog.at_level(logging.INFO):
            handler("test")._send_photo(USER, url)

        assert "secret123" not in caplog.text
        assert "bucket.s3.amazonaws.com" in caplog.text

    def test_the_same_rules_as_messages(self, post):
        assert handler()._send_photo(GUEST, "u") == {"success": False, "skipped_guest": True}
        assert handler()._send_photo(GROUP, "u") == {"success": False}
        post.assert_not_called()
        assert handler()._send_photo(GROUP, "u", force_group=True)["success"] is True

    def test_a_refused_photo(self, post):
        post.return_value = answer(400)

        assert handler()._send_photo(USER, "u") == {"success": False}

    def test_an_album(self, post):
        post.return_value = answer(result=[{"message_id": 1}, {"message_id": 2}])
        media = [{"type": "photo", "media": "a"}, {"type": "photo", "media": "b"}]

        assert handler()._send_media_group(USER, media) == {"success": True, "message_ids": [1, 2]}
        assert method(post) == "sendMediaGroup"
        assert sent(post) == {"chat_id": USER, "media": media}

    def test_an_album_follows_the_same_rules(self, post):
        assert handler()._send_media_group(GUEST, []) == {"success": False, "skipped_guest": True}
        assert handler()._send_media_group(GROUP, []) == {"success": False}
        post.assert_not_called()

    def test_a_refused_album(self, post):
        post.return_value = answer(400)

        assert handler()._send_media_group(USER, []) == {"success": False}


class TestDocuments:
    def test_text_is_sent_as_utf8_with_a_marked_caption(self, post):
        result = handler("test")._send_document_message(USER, "naam;€", "orders.csv", caption="Export")

        assert result == {"success": True, "message_id": 5}
        assert method(post) == "sendDocument"
        assert post.call_args.kwargs["data"] == {"chat_id": USER, "caption": "TEST - Export"}
        name, file, mime = post.call_args.kwargs["files"]["document"]
        assert (name, file.read(), mime) == ("orders.csv", "naam;€".encode(), "text/csv")

    def test_binary_content_is_sent_as_is(self, post):
        handler()._send_document_message(USER, b"PK\x03\x04", "data.zip", mime_type="application/zip")

        _, file, mime = post.call_args.kwargs["files"]["document"]
        assert (file.read(), mime) == (b"PK\x03\x04", "application/zip")

    def test_the_short_form_returns_a_boolean(self, post):
        assert handler()._send_document(USER, "x", "a.csv") is True

        post.return_value = answer(500)
        assert handler()._send_document(USER, "x", "a.csv") is False


class TestOtherCalls:
    def test_delete(self, post):
        assert handler()._delete_message(USER, 9) is True
        assert (method(post), sent(post)) == ("deleteMessage", {"chat_id": USER, "message_id": 9})

        post.return_value = answer(400)
        assert handler()._delete_message(USER, 9) is False

    def test_reaction(self, post):
        assert handler()._set_message_reaction(USER, 9) is True
        assert method(post) == "setMessageReaction"
        assert sent(post)["reaction"] == [{"type": "emoji", "emoji": "👍"}]

        post.return_value = answer(400, text="Bad Request: REACTION_INVALID")
        assert handler()._set_message_reaction(USER, 9, "🍺") is False

    def test_the_simple_send_returns_a_boolean(self, post):
        assert handler()._send_message_simple(USER, "hoi") is True
        assert handler()._send_message_simple(GUEST, "hoi") is False

    @pytest.mark.parametrize(
        ("status", "body", "expected"),
        [
            (200, "", {"success": True, "not_found": False}),
            (400, "Bad Request: message is not modified", {"success": True, "not_found": False}),
            (400, "Bad Request: message to edit not found", {"success": False, "not_found": True}),
            (400, "Bad Request: chat not found", {"success": False, "not_found": True}),
            (429, "Too Many Requests", {"success": False, "not_found": False}),
        ],
    )
    def test_edit(self, post, status, body, expected):
        post.return_value = answer(status, text=body)

        assert handler()._edit_message_text(USER, 9, "nieuw", parse_mode="HTML") == expected
        assert sent(post) == {
            "chat_id": USER,
            "message_id": 9,
            "text": "nieuw",
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        }


class TestBotUsername:
    def test_asked_once_and_remembered(self):
        response = answer(result={"username": "ubbc_bot"})
        with patch("services.telegram_client.requests.get", return_value=response) as get:
            bot = handler()
            assert bot._get_bot_username() == "ubbc_bot"
            assert bot._get_bot_username() == "ubbc_bot"

        get.assert_called_once()

    @pytest.mark.parametrize(("environment", "fallback"), [("test", "ubbc_test_bot"), ("prod", "ubbc_bot")])
    def test_falls_back_to_the_known_name(self, environment, fallback):
        with patch("services.telegram_client.requests.get", side_effect=OSError("down")):
            assert handler(environment)._get_bot_username() == fallback
