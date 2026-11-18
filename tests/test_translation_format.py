"""Every translation can be filled in, and a mistake in one does not break the command that uses it."""

import json
import logging
import string
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import services.translator as translator_module
from handlers.base_handler import BaseHandler
from models.entities import Customer
from services.translator import Translator, load_translations

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


TABLES = {
    "nl": {"greeting": "Hallo {name}", "braces": "Een { open haakje"},
    "en": {"greeting": "Hello {name}", "braces": "A { brace"},
}


@pytest.fixture
def db():
    db = Mock()
    db.get_customer_by_telegram_id.return_value = None
    return db


@pytest.fixture
def translator(db):
    return Translator(db, tables=TABLES.__getitem__)


def test_placeholders_are_filled_in(translator):
    assert translator.translate("greeting", name="Jan") == "Hallo Jan"


def test_a_missing_placeholder_gives_the_unfilled_text_and_logs_the_key(translator, caplog):
    with caplog.at_level(logging.ERROR):
        assert translator.translate("greeting", naam="Jan") == "Hallo {name}"

    assert "'greeting'" in caplog.text
    assert "Jan" not in caplog.text  # the parameters are never logged


def test_a_stray_brace_gives_the_unfilled_text(translator):
    assert translator.translate("braces", name="Jan") == "Een { open haakje"


def test_without_parameters_the_text_is_not_formatted(translator):
    assert translator.translate("braces") == "Een { open haakje"


def test_an_unknown_key_is_returned_as_is(translator):
    assert translator.translate("does_not_exist") == "does_not_exist"


class TestLanguage:
    def test_the_customers_choice(self, translator, db):
        db.get_customer_by_telegram_id.return_value = Customer(telegram_user_id=7, language="en")

        assert translator.translate("greeting", 7, name="Jan") == "Hello Jan"
        db.get_customer_by_telegram_id.assert_called_once_with(7)

    def test_dutch_without_a_customer_or_a_user(self, translator, db):
        assert translator.language(7) == "nl"
        assert translator.language(None) == "nl"

    def test_group_messages_are_always_dutch(self, translator, db):
        db.get_customer_by_telegram_id.return_value = Customer(telegram_user_id=7, language="en")

        assert translator.translate("greeting", 7, force_group_lang=True, name="Jan") == "Hallo Jan"


class TestLoading:
    def test_each_file_is_read_once_per_container(self, monkeypatch):
        monkeypatch.setattr(translator_module, "_loaded", {})
        with patch.object(Path, "read_text", wraps=Path.read_text, autospec=True) as read:
            first = load_translations("nl")
            assert load_translations("nl") is first

        assert read.call_count == 1

    def test_an_unknown_language_gets_dutch(self):
        assert load_translations("de") is load_translations("nl")

    def test_an_unreadable_file_falls_back_to_english(self, monkeypatch):
        monkeypatch.setattr(translator_module, "_loaded", {})
        monkeypatch.setattr(translator_module, "TRANSLATIONS_DIR", Path("/does/not/exist"))
        english = {"hello": "Hello"}

        def read_text(path, encoding=None):
            if path.name == "en.json":
                return json.dumps(english)
            raise OSError("gone")

        with patch.object(Path, "read_text", read_text):
            assert load_translations("nl") == english

    def test_the_handler_uses_the_shared_tables(self, db):
        handler = BaseHandler(db, 1, "prod", "token")

        assert handler._load_translations("en") is load_translations("en")
        assert handler._t("unknown") == load_translations("nl")["unknown"]
