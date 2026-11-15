"""Central PII redaction for log output.

Defense in depth: call sites should log identifiers (customer_id / Telegram user ID) instead of
names, but a filter on the root logger masks the known PII shapes so a new log line cannot
leak them by accident.
"""

import logging
import re

REDACTED = "***"

# Telegram handles: "@name". The lookbehind skips e-mail addresses and word-embedded "@".
_HANDLE_PATTERN = re.compile(r"(?<![\w@])@\w{2,}")

# Known PII fields rendered as key=value, key: value, 'key': 'value' or "key": "value".
_PII_KEYS = (
    "first_name",
    "last_name",
    "username",
    "display_name",
    "full_name",
    "contact_info",
    "contact",
)
_FIELD_PATTERN = re.compile(
    r"(?P<key>\b(?:" + "|".join(_PII_KEYS) + r")\b['\"]?\s*[:=]\s*)"
    r"(?:'[^']*'|\"[^\"]*\"|None|[^\s,}\])]+)",
    re.IGNORECASE,
)


def redact(message: str) -> str:
    """Mask Telegram handles and known PII fields in a log message."""
    message = _FIELD_PATTERN.sub(lambda m: m.group("key") + REDACTED, message)
    return _HANDLE_PATTERN.sub("@" + REDACTED, message)


class PiiRedactionFilter(logging.Filter):
    """Logging filter that redacts PII from the fully formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except TypeError, ValueError, KeyError:
            # A malformed format string must not hide the log line, but also must not leak args.
            record.msg = str(record.msg)
            record.args = None
            return True
        record.msg = redact(message)
        record.args = None
        return True


def install_pii_redaction() -> None:
    """Attach the redaction filter to the root logger and its handlers (idempotent).

    The Lambda runtime installs its handler on the root logger before user code is imported.
    Filters on a handler apply to records from every logger, including child loggers such as
    ``logging.getLogger(__name__)``, which a filter on the root logger alone would miss.
    """
    root = logging.getLogger()
    targets: list[logging.Filterer] = [root, *root.handlers]
    for target in targets:
        if not any(isinstance(f, PiiRedactionFilter) for f in target.filters):
            target.addFilter(PiiRedactionFilter())
