"""Expiry of exported files sent to the admin chat.

An export (/export_orders) contains customer data, so the CSV message is removed from the chat
an hour after it was sent. There is no scheduler: the sent message is tracked in the notifications
table (kind "export", offer_id 0) and expired exports are deleted whenever one of these events
happens: a new export, an offer publish or announcement, an offer message sync, or an update
from the admin.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from models.entities import NotificationMessage

logger = logging.getLogger()

EXPORT_KIND = "export"
EXPORT_OFFER_ID = 0  # Export rows belong to no offer. Real offer IDs start at 1.
EXPORT_LIFETIME_SECONDS = 60 * 60

# The tracking row must outlive the message deadline, otherwise DynamoDB's TTL could remove the
# row before the message is deleted and the file would stay in the chat.
ROW_GRACE_SECONDS = 24 * 60 * 60

# Cap on sweeps per warm container, so frequent triggers cost at most one small query a minute.
SWEEP_INTERVAL_SECONDS = 60


class ExportExpiryService:
    _last_sweep: float = 0.0

    def __init__(
        self, db, delete_message: Callable[[int, int], dict[str, Any]], clock: Callable[[], float] = time.time
    ):
        """``delete_message(chat_id, message_id)`` returns {"success": bool, "gone": bool}"""
        self.db = db
        self._delete_message = delete_message
        self._clock = clock

    def track(self, chat_id: int, message_id: int) -> bool:
        """Record an export message so it is deleted after EXPORT_LIFETIME_SECONDS"""
        expires_at = int(self._clock()) + EXPORT_LIFETIME_SECONDS
        row = NotificationMessage(
            offer_id=EXPORT_OFFER_ID,
            chat_id=chat_id,
            message_id=message_id,
            kind=EXPORT_KIND,
            expires_at=expires_at,
            ttl=expires_at + ROW_GRACE_SECONDS,
        )
        return bool(self.db.create_notification_message(row))

    def sweep(self, force: bool = False) -> int:
        """Delete expired export messages. Returns the number of tracking rows removed. Never raises."""
        try:
            now = self._clock()
            if not force and now - ExportExpiryService._last_sweep < SWEEP_INTERVAL_SECONDS:
                return 0
            ExportExpiryService._last_sweep = now

            removed = 0
            for row in self.db.get_notification_messages_by_offer(EXPORT_OFFER_ID):
                if row.kind != EXPORT_KIND or row.expires_at is None or row.expires_at > now:
                    continue
                if self._expire(row):
                    removed += 1
            return removed
        except Exception as e:
            logger.error(f"Error expiring exports: {e}")
            return 0

    def _expire(self, row: NotificationMessage) -> bool:
        result = self._delete_message(row.chat_id, row.message_id)
        if result.get("success"):
            pass
        elif result.get("gone"):
            # Already deleted, or older than Telegram's 48 hour limit for deleting messages.
            # Retrying cannot help, so the row is dropped.
            logger.warning(f"Export message {row.message_id} could not be deleted (gone or too old)")
        else:
            return False  # Transient failure: keep the row and retry on the next sweep

        return bool(self.db.delete_notification_message(row.notification_id))
