"""User-facing texts in the user's language (src/translations/nl.json and en.json).

The files are read once per Lambda container, not once per handler: BotService builds about twenty handlers for
every request, and each of them used to read the JSON again.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger()

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "translations"
LANGUAGES = ("nl", "en")
DEFAULT_LANGUAGE = "nl"  # customers without a preference, the admin, and every group message

_loaded: dict[str, dict[str, str]] = {}


def load_translations(lang: str) -> dict[str, str]:
    """All texts of a language. An unknown language gets Dutch; a file that cannot be read falls back to English."""
    lang_file = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
    if lang_file not in _loaded:
        try:
            _loaded[lang_file] = json.loads((TRANSLATIONS_DIR / f"{lang_file}.json").read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Error loading translations for {lang_file}: {e}")
            return load_translations("en") if lang_file != "en" else {}
    return _loaded[lang_file]


class Translator:
    def __init__(self, db, tables: Callable[[str], dict[str, str]] = load_translations):
        self.db = db
        self.tables = tables

    def language(self, user_id: int | None) -> str:
        """The customer's chosen language; Dutch when there is no customer record or no choice"""
        if user_id:
            customer = self.db.get_customer_by_telegram_id(user_id)
            if customer and getattr(customer, "language", None):
                return customer.language
        return DEFAULT_LANGUAGE

    def translate(self, key: str, user_id: int | None = None, force_group_lang: bool = False, **params) -> str:
        """The text of ``key`` with ``params`` filled in. Group messages are always Dutch.

        An unknown key is returned as is. A text that cannot be filled in (a placeholder the caller does not pass, a
        stray brace) is returned unfilled, so one wrong translation never breaks a command.
        """
        lang = DEFAULT_LANGUAGE if force_group_lang else self.language(user_id)
        return text(lang, key, self.tables, **params)


def text(lang: str, key: str, tables: Callable[[str], dict[str, str]] = load_translations, **params) -> str:
    """The text of ``key`` in ``lang``, for code that knows the language and has no database (the Lambdas)"""
    message = tables(lang).get(key, key)
    if not params:
        return message
    try:
        return message.format(**params)
    except (KeyError, IndexError, ValueError) as e:
        # Only the key and the error are logged, never the parameters
        logger.error(f"Translation {key!r} ({lang}) could not be filled in: {type(e).__name__}: {e}")
        return message
