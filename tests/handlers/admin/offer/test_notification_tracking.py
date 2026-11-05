"""Tests for capturing announcement message ids (Step 3).

The group announcement and each subscriber DM must record a NotificationMessage
(with the returned Telegram message_id and the correct ``kind``) so the message
can later be edited on a status/content change.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from handlers.admin.offer.notifications import NotificationHandler
from models.entities import NotificationMessage, Offer, OfferStatus


@pytest.fixture
def offer():
    return Offer(
        offer_id=42,
        name="Tripel",
        description="Strong golden ale",
        price_per_unit=Decimal("4.50"),
        status=OfferStatus.ACTIVE.value,
    )


@pytest.fixture
def handler():
    db = MagicMock()
    db.create_notification_message.return_value = True
    h = NotificationHandler(db, admin_user_id=1, environment="test", telegram_token="t")
    h._get_bot_username = MagicMock(return_value="ubbc_test_bot")
    h._send_photo = MagicMock()
    h._send_media_group = MagicMock()
    h._t = MagicMock(side_effect=lambda key, *a, **k: key)
    h._send_message = MagicMock(return_value={"success": True, "message_id": 555})
    return h


class TestNotificationTracking:
    def test_group_announcement_records_group_row(self, handler, offer):
        handler._send_rich_offer_message(chat_id=-100, offer=offer, force_group=True, include_buttons=False)

        handler.db.create_notification_message.assert_called_once()
        stored = handler.db.create_notification_message.call_args[0][0]
        assert isinstance(stored, NotificationMessage)
        assert stored.offer_id == 42
        assert stored.chat_id == -100
        assert stored.message_id == 555
        assert stored.kind == "group"

    def test_preview_does_not_record(self, handler, offer):
        handler._send_rich_offer_message(chat_id=123, offer=offer, preview=True)
        handler.db.create_notification_message.assert_not_called()

    def test_failed_send_does_not_record(self, handler, offer):
        handler._send_message.return_value = {"success": False}
        handler._send_rich_offer_message(chat_id=-100, offer=offer, force_group=True)
        handler.db.create_notification_message.assert_not_called()

    def test_subscriber_dm_records_subscriber_row(self, handler, offer):
        handler._send_optimized_rich_message(chat_id=999, offer=offer, presigned_images=[])

        handler.db.create_notification_message.assert_called_once()
        stored = handler.db.create_notification_message.call_args[0][0]
        assert stored.chat_id == 999
        assert stored.message_id == 555
        assert stored.kind == "subscriber"

    def test_simple_notification_records_subscriber_row(self, handler, offer):
        handler._send_simple_offer_notification(chat_id=888, offer=offer)

        stored = handler.db.create_notification_message.call_args[0][0]
        assert stored.chat_id == 888
        assert stored.kind == "subscriber"

    def test_ttl_set_about_168h_out(self):
        before = datetime.now(UTC)
        msg = NotificationMessage(offer_id=1, chat_id=2, message_id=3)
        expected = int((before + timedelta(hours=168)).timestamp())
        # Allow a small clock drift during the test run.
        assert abs(msg.ttl - expected) <= 5

    def test_ttl_handles_string_created_at(self):
        created = "2026-01-01T00:00:00+00:00"
        msg = NotificationMessage(offer_id=1, chat_id=2, message_id=3, created_at=created)
        expected = int((datetime.fromisoformat(created) + timedelta(hours=168)).timestamp())
        assert msg.ttl == expected
