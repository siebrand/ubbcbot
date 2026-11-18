"""The Telegram Bot API over HTTP: one place for the URL, the token, the timeout and the error handling.

Only the transport lives here. What a message may be sent to (guests, group chats in production) and how it is
marked in the test environment are decided by the callers (BaseHandler), per kind of message.
"""

import logging
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger()

API_URL = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class TelegramResponse:
    """What came back. ``status_code`` is None when there was no answer (no token, network error, timeout)."""

    ok: bool
    status_code: int | None = None
    body: str = ""
    result: Any = None  # the "result" of a successful call: a Message, a list of them, True, ...

    def says(self, *phrases: str) -> bool:
        """Whether Telegram's error description contains one of the phrases (case-insensitive)"""
        lowered = self.body.lower()
        return any(phrase.lower() in lowered for phrase in phrases)

    @property
    def message_id(self) -> int | None:
        return self.result.get("message_id") if isinstance(self.result, dict) else None


class TelegramClient:
    def __init__(self, token: str):
        self.token = token

    def call(
        self, method: str, payload: dict[str, Any] | None = None, files: dict | None = None, get: bool = False
    ) -> TelegramResponse:
        """Call a Bot API method. Never raises: a failure is a response with ``ok`` False.

        ``payload`` is sent as JSON, or as form fields when ``files`` are uploaded. ``get`` sends a GET without body.
        """
        if not self.token:
            logger.error("Telegram token is empty")
            return TelegramResponse(ok=False)

        url = API_URL.format(token=self.token, method=method)
        try:
            if get:
                response = requests.get(url, timeout=TIMEOUT_SECONDS)
            elif files is not None:
                response = requests.post(url, data=payload, files=files, timeout=TIMEOUT_SECONDS)
            else:
                response = requests.post(url, json=payload, timeout=TIMEOUT_SECONDS)
        except Exception as e:
            # Only the type: the message of a requests exception contains the URL, and so the token
            logger.error(f"Telegram {method} failed: {type(e).__name__}")
            return TelegramResponse(ok=False)

        body = response.text if isinstance(response.text, str) else ""
        if response.status_code != 200:
            return TelegramResponse(ok=False, status_code=response.status_code, body=body)
        try:
            result = response.json()["result"]
        except Exception:
            result = None
        return TelegramResponse(ok=True, status_code=200, body=body, result=result)
