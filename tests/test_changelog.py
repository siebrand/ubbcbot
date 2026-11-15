"""Every changelog page is sent as one message: Telegram rejects a message over 4096 characters (as shown, UTF-16).

The tests call the real handler and measure what it sends, so a change in how a page is built is measured too.
"""

import html
import re
from unittest.mock import Mock

import pytest

from handlers.customer.changelog_commands import ChangelogCommands

TELEGRAM_MESSAGE_LIMIT = 4096
CHAT_ID = 1
USER_ID = 1


def _handler() -> ChangelogCommands:
    handler = ChangelogCommands(Mock(), 1, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    return handler


PAGES = list(range(1, len(_handler().changelog_entries) + 1))


def _sent_page(page: int):
    handler = _handler()
    result = handler.handle_changelog(CHAT_ID, USER_ID, page)
    assert result == {"status": "success"}
    handler._send_message.assert_called_once()
    return handler._send_message.call_args


def _shown_length(text: str) -> int:
    shown = html.unescape(re.sub(r"<[^>]+>", "", text))
    return len(shown.encode("utf-16-le")) // 2


def test_there_are_pages_to_test():
    assert len(PAGES) > 5


@pytest.mark.parametrize("page", PAGES)
def test_a_page_fits_in_one_telegram_message(page):
    sent = _sent_page(page)

    assert _shown_length(sent.args[1]) <= TELEGRAM_MESSAGE_LIMIT


@pytest.mark.parametrize("page", PAGES)
def test_the_html_of_a_page_is_balanced(page):
    """An unclosed tag makes Telegram reject the message"""
    sent = _sent_page(page)

    assert sent.kwargs["parse_mode"] == "HTML"
    for tag in ("b", "code", "i"):
        assert sent.args[1].count(f"<{tag}>") == sent.args[1].count(f"</{tag}>"), tag


@pytest.mark.parametrize("page", PAGES)
def test_a_page_has_the_title_of_its_entry(page):
    handler = _handler()

    handler.handle_changelog(CHAT_ID, USER_ID, page)

    assert handler.changelog_entries[page - 1]["title"] in handler._send_message.call_args.args[1]
