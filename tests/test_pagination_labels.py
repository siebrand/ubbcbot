"""The page buttons carry no words, so they read the same in every language (audit 4, B8)"""

import pytest

from utils.pagination import PaginationUtils


def buttons(page: int, total: int, enhanced: bool) -> list[dict]:
    keyboard = PaginationUtils.build_pagination_keyboard(page, total, "changelog", enhanced=enhanced)
    return [b for row in keyboard["inline_keyboard"] for b in row]


@pytest.mark.parametrize("enhanced", [False, True])
@pytest.mark.parametrize("page", [1, 2, 3])
def test_no_button_has_a_word(enhanced, page):
    for button in buttons(page, 3, enhanced):
        assert not any(c.isalpha() for c in button["text"]), button["text"]


def test_the_plain_buttons_go_back_show_the_page_and_go_on():
    assert [(b["text"], b["callback_data"]) for b in buttons(2, 3, enhanced=False)] == [
        ("◀️", "page_changelog_1"),
        ("2/3", "page_info"),
        ("▶️", "page_changelog_3"),
    ]
