"""Every translation can be filled in, and a mistake in one does not break the command that uses it."""

import json
import logging
import string
from pathlib import Path
from unittest.mock import Mock

import pytest

from handlers.base_handler import BaseHandler

TRANSLATIONS = Path(__file__).parent.parent / "src" / "translations"


class Anything:
    """A placeholder value that accepts every format spec ({amount:.2f}, {count:>3}, ...)"""

    def __format__(self, spec):
        return "x"


def translations(lang: str) -> dict[str, str]:
    return json.loads((TRANSLATIONS / f"{lang}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("lang", ["nl", "en"])
def test_every_translation_can_be_filled_in(lang):
    broken = []
    for key, text in translations(lang).items():
        try:
            fields = {name for _, name, _, _ in string.Formatter().parse(text) if name}
            text.format(**dict.fromkeys(fields, Anything()))
        except (KeyError, IndexError, ValueError) as e:
            broken.append(f"{key}: {e}")

    assert broken == []


@pytest.fixture
def handler():
    db = Mock()
    db.get_customer_by_telegram_id.return_value = None
    handler = BaseHandler(db, 1, "prod", "token")
    handler._translations["nl"] = {"greeting": "Hallo {name}", "braces": "Een { open haakje", "plain": "Hoi"}
    return handler


def test_placeholders_are_filled_in(handler):
    assert handler._t("greeting", name="Jan") == "Hallo Jan"


def test_a_missing_placeholder_gives_the_unfilled_text_and_logs_the_key(handler, caplog):
    with caplog.at_level(logging.ERROR):
        assert handler._t("greeting", naam="Jan") == "Hallo {name}"

    assert "'greeting'" in caplog.text
    assert "Jan" not in caplog.text  # the parameters are never logged


def test_a_stray_brace_gives_the_unfilled_text(handler):
    assert handler._t("braces", name="Jan") == "Een { open haakje"


def test_without_parameters_the_text_is_not_formatted(handler):
    assert handler._t("braces") == "Een { open haakje"


def test_an_unknown_key_is_returned_as_is(handler):
    assert handler._t("does_not_exist") == "does_not_exist"
