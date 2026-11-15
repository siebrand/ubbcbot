"""Tests for the central PII redaction logging filter."""

import logging

import pytest

from utils.log_redaction import REDACTED, PiiRedactionFilter, install_pii_redaction, redact


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
