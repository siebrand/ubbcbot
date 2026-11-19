"""The Bot API transport: URL, token, timeout, error handling and what a response says."""

import logging
from unittest.mock import Mock, patch

import pytest
import requests
from conftest import FAKE_TOKEN

from services.telegram_client import TIMEOUT_SECONDS, TelegramClient, TelegramResponse

TOKEN = FAKE_TOKEN


def answer(status=200, json=None, text=""):
    response = Mock(status_code=status, text=text)
    response.json.return_value = json if json is not None else {"ok": True, "result": True}
    return response


@pytest.fixture
def post():
    with patch("services.telegram_client.requests.post") as post:
        yield post


class TestCall:
    def test_posts_json_to_the_method_with_a_timeout(self, post):
        post.return_value = answer(json={"ok": True, "result": {"message_id": 7}})

        response = TelegramClient(TOKEN).call("sendMessage", {"chat_id": 1, "text": "hoi"})

        post.assert_called_once_with(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": 1, "text": "hoi"},
            timeout=TIMEOUT_SECONDS,
        )
        assert response == TelegramResponse(ok=True, status_code=200, body="", result={"message_id": 7})
        assert response.message_id == 7

    def test_files_are_sent_as_a_form(self, post):
        post.return_value = answer()
        files = {"document": ("a.csv", b"x", "text/csv")}

        TelegramClient(TOKEN).call("sendDocument", {"chat_id": 1}, files=files)

        assert post.call_args.kwargs == {"data": {"chat_id": 1}, "files": files, "timeout": TIMEOUT_SECONDS}

    def test_get_sends_no_body(self):
        with patch(
            "services.telegram_client.requests.get", return_value=answer(json={"result": {"username": "b"}})
        ) as get:
            response = TelegramClient(TOKEN).call("getMe", get=True)

        get.assert_called_once_with(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=TIMEOUT_SECONDS)
        assert response.result == {"username": "b"}

    def test_without_a_token_nothing_is_sent(self, post, caplog):
        with caplog.at_level(logging.ERROR):
            response = TelegramClient("").call("sendMessage", {})

        post.assert_not_called()
        assert response == TelegramResponse(ok=False)
        assert "Telegram token is empty" in caplog.text

    def test_an_error_answer_keeps_the_status_and_description(self, post):
        post.return_value = answer(400, text='{"ok":false,"description":"Bad Request: chat not found"}')

        response = TelegramClient(TOKEN).call("sendMessage", {})

        assert (response.ok, response.status_code) == (False, 400)
        assert response.says("CHAT NOT FOUND", "something else")
        assert not response.says("message is not modified")
        assert response.message_id is None

    def test_a_network_error_is_a_failed_response_and_the_token_is_not_logged(self, post, caplog):
        post.side_effect = requests.ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/sendMessage")

        with caplog.at_level(logging.ERROR):
            response = TelegramClient(TOKEN).call("sendMessage", {})

        assert response == TelegramResponse(ok=False)
        assert "sendMessage failed: ConnectionError" in caplog.text
        assert TOKEN not in caplog.text

    def test_a_200_without_json_has_no_result(self, post):
        response = answer()
        response.json.side_effect = ValueError("not json")
        post.return_value = response

        assert TelegramClient(TOKEN).call("deleteMessage", {}) == TelegramResponse(ok=True, status_code=200)

    def test_get_with_parameters(self):
        with patch("services.telegram_client.requests.get", return_value=answer()) as get:
            TelegramClient(TOKEN).call("getFile", {"file_id": "f1"}, get=True)

        assert get.call_args.kwargs == {"params": {"file_id": "f1"}, "timeout": TIMEOUT_SECONDS}

    def test_a_list_result_has_no_single_message_id(self, post):
        post.return_value = answer(json={"result": [{"message_id": 1}, {"message_id": 2}]})

        response = TelegramClient(TOKEN).call("sendMediaGroup", {})

        assert response.result == [{"message_id": 1}, {"message_id": 2}]
        assert response.message_id is None


class TestDownloadFile:
    def downloads(self, *answers):
        return patch("services.telegram_client.requests.get", side_effect=list(answers))

    def test_asks_for_the_path_then_downloads_the_content(self):
        file = Mock(status_code=200, content=b"bytes")
        with self.downloads(answer(json={"result": {"file_path": "photos/a.jpg"}}), file) as get:
            assert TelegramClient(TOKEN).download_file("f1") == b"bytes"

        assert get.call_args_list[0].kwargs["params"] == {"file_id": "f1"}
        assert get.call_args_list[1].args[0] == f"https://api.telegram.org/file/bot{TOKEN}/photos/a.jpg"

    def test_an_unknown_file(self):
        with self.downloads(answer(400, text="Bad Request: invalid file_id")) as get:
            assert TelegramClient(TOKEN).download_file("f1") is None

        assert get.call_count == 1

    def test_a_failed_download(self):
        with self.downloads(answer(json={"result": {"file_path": "a"}}), Mock(status_code=404)):
            assert TelegramClient(TOKEN).download_file("f1") is None

    def test_a_network_error_while_downloading_does_not_log_the_token(self, caplog):
        error = requests.ConnectionError(f"/file/bot{TOKEN}/a")
        with self.downloads(answer(json={"result": {"file_path": "a"}}), error), caplog.at_level(logging.ERROR):
            assert TelegramClient(TOKEN).download_file("f1") is None

        assert "download failed: ConnectionError" in caplog.text
        assert TOKEN not in caplog.text
