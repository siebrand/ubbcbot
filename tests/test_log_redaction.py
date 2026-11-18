"""Tests for the central PII redaction logging filter."""

import logging

import pytest

from utils.log_redaction import REDACTED, PiiRedactionFilter, configure_logging, install_pii_redaction, redact


class TestRedact:
    def test_masks_telegram_handle(self):
        assert redact("User: Jan (@jan_de_vries) | ID: 42") == f"User: Jan (@{REDACTED}) | ID: 42"

    def test_keeps_email_like_text_untouched(self):
        assert redact("mail info@example.com") == "mail info@example.com"

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("first_name=Jan", f"first_name={REDACTED}"),
            ("last_name: Vries", f"last_name: {REDACTED}"),
            ("{'first_name': 'Jan van', 'id': 5}", f"{{'first_name': {REDACTED}, 'id': 5}}"),
            ('{"username": "jan", "id": 5}', f'{{"username": {REDACTED}, "id": 5}}'),
            ("contact_info=None", f"contact_info={REDACTED}"),
            ("USERNAME=jan", f"USERNAME={REDACTED}"),
        ],
    )
    def test_masks_known_pii_fields(self, raw, expected):
        assert redact(raw) == expected

    def test_does_not_touch_identifiers(self):
        message = "Order 12 for customer_id abc-123 telegram_user_id=99"
        assert redact(message) == message

    def test_does_not_match_keys_inside_longer_words(self):
        assert redact("contactless=yes") == "contactless=yes"

    def test_masks_a_bot_token_in_a_request_url(self):
        token = "1234567890:XXX-abcdefghijklmnopqrstuvwxyz_0123"
        error = (
            "HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded with url: "
            f"/bot{token}/sendMessage (Caused by NewConnectionError)"
        )

        redacted = redact(error)

        assert token not in redacted
        assert f"/bot{REDACTED}/sendMessage" in redacted

    def test_does_not_touch_times_or_ids_that_look_a_little_like_a_token(self):
        message = "Order 12:30 for chat -1001234567890 message_id=42 at 2026-11-19T10:00:00"
        assert redact(message) == message


class TestFilter:
    def _record(self, msg, *args):
        return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args or None, None)

    def test_redacts_formatted_args(self):
        record = self._record("seen %s (@%s)", "x", "someone")
        assert PiiRedactionFilter().filter(record) is True
        assert record.getMessage() == f"seen x (@{REDACTED})"

    def test_malformed_format_does_not_raise_or_leak_args(self):
        record = self._record("bad %d", "@secret_user")
        assert PiiRedactionFilter().filter(record) is True
        assert "secret_user" not in record.getMessage()


class TestConfigureLogging:
    @pytest.fixture
    def clean_root(self):
        root = logging.getLogger()
        saved = (root.level, list(root.filters), list(root.handlers))
        root.filters = []
        yield root
        root.setLevel(saved[0])
        root.filters, root.handlers = saved[1], saved[2]

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("WARNING", logging.WARNING),
            ("warning", logging.WARNING),
            ("DEBUG", logging.DEBUG),
            (None, logging.INFO),
            ("NOPE", logging.INFO),
            ("", logging.INFO),
        ],
    )
    def test_level_comes_from_environment(self, clean_root, monkeypatch, value, expected):
        if value is None:
            monkeypatch.delenv("LOG_LEVEL", raising=False)
        else:
            monkeypatch.setenv("LOG_LEVEL", value)

        configure_logging()

        assert clean_root.level == expected

    def test_also_installs_redaction(self, clean_root, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "INFO")

        configure_logging()

        assert any(isinstance(f, PiiRedactionFilter) for f in clean_root.filters)


class TestInstall:
    @pytest.fixture
    def clean_root(self):
        root = logging.getLogger()
        saved_filters, saved_handlers = list(root.filters), list(root.handlers)
        root.filters = []
        yield root
        root.filters, root.handlers = saved_filters, saved_handlers

    def test_install_is_idempotent(self, clean_root):
        handler = logging.StreamHandler()
        clean_root.addHandler(handler)
        install_pii_redaction()
        install_pii_redaction()
        assert sum(isinstance(f, PiiRedactionFilter) for f in clean_root.filters) == 1
        assert sum(isinstance(f, PiiRedactionFilter) for f in handler.filters) == 1

    def test_child_logger_output_is_redacted_by_handler(self, clean_root):
        records: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        clean_root.addHandler(Capture())
        install_pii_redaction()
        child = logging.getLogger("repositories.customer_repository")
        child.warning("failed for user (@jan_de_vries) first_name=Jan")
        assert records == [f"failed for user (@{REDACTED}) first_name={REDACTED}"]
