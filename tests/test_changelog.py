"""Every changelog entry is sent as one message: Telegram rejects a message over 4096 characters (as shown, UTF-16)."""

import html
import re
from unittest.mock import Mock

import pytest

from handlers.customer.changelog_commands import ChangelogCommands

TELEGRAM_MESSAGE_LIMIT = 4096

ENTRIES = ChangelogCommands(Mock(), 1, "test", "token").changelog_entries


def _shown_length(entry: dict) -> int:
    message = f"📋 <b>UBBC Bot Changelog</b>\n\n<b>{entry['title']}</b>\n\n{entry['content']}"
    shown = html.unescape(re.sub(r"<[^>]+>", "", message))
    return len(shown.encode("utf-16-le")) // 2


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["title"] for e in ENTRIES])
def test_an_entry_fits_in_one_telegram_message(entry):
    assert _shown_length(entry) <= TELEGRAM_MESSAGE_LIMIT


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["title"] for e in ENTRIES])
def test_the_html_of_an_entry_is_balanced(entry):
    """An unclosed tag makes Telegram reject the message"""
    for tag in ("b", "code", "i"):
        assert entry["content"].count(f"<{tag}>") == entry["content"].count(f"</{tag}>"), tag
