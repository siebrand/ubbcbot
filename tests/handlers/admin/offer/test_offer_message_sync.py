"""Tests for the message-edit helper and sync_offer_messages (Step 4)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from handlers.admin.offer.notifications import NotificationHandler
from handlers.base_handler import BaseHandler
from models.entities import NotificationMessage, Offer, OfferStatus


def _resp(status_code, text="{}"):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.json.return_value = {"ok": True, "result": {"message_id": 1}}
    return r


class TestEditMessageText:
    def _handler(self):
        return BaseHandler(MagicMock(), admin_user_id=1, environment="test", telegram_token="t")

    def test_success(self):
        h = self._handler()
        with patch("handlers.base_handler.requests.post", return_value=_resp(200)):
            result = h._edit_message_text(123, 456, "hi", parse_mode="HTML")
        assert result == {"success": True, "not_found": False}

    def test_message_not_modified_is_success(self):
        h = self._handler()
        with patch(
            "handlers.base_handler.requests.post",
            return_value=_resp(400, "Bad Request: message is not modified"),
        ):
            result = h._edit_message_text(1, 2, "hi")
        assert result["success"] is True
        assert result["not_found"] is False

    def test_message_not_found(self):
        h = self._handler()
        with patch(
            "handlers.base_handler.requests.post",
            return_value=_resp(400, "Bad Request: message to edit not found"),
        ):
            result = h._edit_message_text(1, 2, "hi")
        assert result == {"success": False, "not_found": True}

    def test_other_error(self):
        h = self._handler()
        with patch("handlers.base_handler.requests.post", return_value=_resp(400, "Bad Request: something else")):
            result = h._edit_message_text(1, 2, "hi")
        assert result == {"success": False, "not_found": False}

    def test_empty_token(self):
        h = BaseHandler(MagicMock(), 1, "test", "")
        assert h._edit_message_text(1, 2, "hi")["success"] is False

    def test_reply_markup_omitted_when_none(self):
        h = self._handler()
        with patch("handlers.base_handler.requests.post", return_value=_resp(200)) as post:
            h._edit_message_text(1, 2, "hi", reply_markup=None)
        assert "reply_markup" not in post.call_args.kwargs["json"]

    def test_empty_keyboard_sent_to_remove_buttons(self):
        h = self._handler()
        with patch("handlers.base_handler.requests.post", return_value=_resp(200)) as post:
            h._edit_message_text(1, 2, "hi", reply_markup={"inline_keyboard": []})
        assert post.call_args.kwargs["json"]["reply_markup"] == {"inline_keyboard": []}


@pytest.fixture
def active_offer():
    return Offer(
        offer_id=7,
        name="Dubbel",
        description="Dark",
        price_per_unit=Decimal("3.00"),
        status=OfferStatus.ACTIVE.value,
    )


@pytest.fixture
def sync_handler(active_offer):
    db = MagicMock()
    db.get_offer.return_value = active_offer
    h = NotificationHandler(db, admin_user_id=1, environment="test", telegram_token="t")
    h._get_bot_username = MagicMock(return_value="ubbc_test_bot")
    h._t = MagicMock(side_effect=lambda key, *a, **k: key)
    h._edit_message_text = MagicMock(return_value={"success": True, "not_found": False})
    return h


def _row(notification_id, chat_id, message_id, kind):
    return NotificationMessage(
        notification_id=notification_id, offer_id=7, chat_id=chat_id, message_id=message_id, kind=kind
    )


class TestSyncOfferMessages:
    def test_missing_offer_noops(self, sync_handler):
        sync_handler.db.get_offer.return_value = None
        sync_handler.sync_offer_messages(7)
        sync_handler._edit_message_text.assert_not_called()

    def test_edits_group_then_subscribers(self, sync_handler):
        sync_handler.db.get_notification_messages_by_offer.return_value = [
            _row("s1", 11, 100, "subscriber"),
            _row("g1", -500, 200, "group"),
        ]
        sync_handler.sync_offer_messages(7)

        # Group edited first.
        first_chat = sync_handler._edit_message_text.call_args_list[0].args[0]
        assert first_chat == -500
        assert sync_handler._edit_message_text.call_count == 2

    def test_active_offer_group_has_buttons(self, sync_handler):
        # Group order buttons are enabled; an active offer re-render keeps them.
        sync_handler.db.get_notification_messages_by_offer.return_value = [_row("g1", -500, 200, "group")]
        sync_handler.sync_offer_messages(7)
        markup = sync_handler._edit_message_text.call_args.kwargs["reply_markup"]
        assert markup["inline_keyboard"]  # non-empty = order buttons present

    def test_active_offer_subscriber_keeps_buttons(self, sync_handler):
        sync_handler.db.get_notification_messages_by_offer.return_value = [_row("s1", 55, 200, "subscriber")]
        sync_handler.sync_offer_messages(7)
        markup = sync_handler._edit_message_text.call_args.kwargs["reply_markup"]
        assert markup["inline_keyboard"]  # non-empty = order buttons present

    def test_cancelled_removes_buttons(self, sync_handler):
        sync_handler.db.get_notification_messages_by_offer.return_value = [_row("g1", -500, 200, "group")]
        sync_handler.sync_offer_messages(7, cancelled=True)
        markup = sync_handler._edit_message_text.call_args.kwargs["reply_markup"]
        assert markup == {"inline_keyboard": []}

    def test_sold_out_removes_buttons(self, sync_handler, active_offer):
        active_offer.status = OfferStatus.SOLD_OUT.value
        sync_handler.db.get_notification_messages_by_offer.return_value = [_row("g1", -500, 200, "group")]
        sync_handler.sync_offer_messages(7)
        markup = sync_handler._edit_message_text.call_args.kwargs["reply_markup"]
        assert markup == {"inline_keyboard": []}

    def test_prunes_row_on_not_found(self, sync_handler):
        sync_handler._edit_message_text.return_value = {"success": False, "not_found": True}
        sync_handler.db.get_notification_messages_by_offer.return_value = [_row("g1", -500, 200, "group")]
        sync_handler.sync_offer_messages(7)
        sync_handler.db.delete_notification_message.assert_called_once_with("g1")

    def test_large_subscriber_count_goes_async(self, sync_handler):
        rows = [_row(f"s{i}", i, i + 1000, "subscriber") for i in range(11)]
        rows.append(_row("g1", -500, 200, "group"))
        sync_handler.db.get_notification_messages_by_offer.return_value = rows
        with patch.object(sync_handler, "_sync_subscriber_messages_async") as async_mock:
            sync_handler.sync_offer_messages(7)
        async_mock.assert_called_once_with(7, False)
        # Only the single group row edited inline; subscribers handed off.
        assert sync_handler._edit_message_text.call_count == 1

    def test_small_subscriber_count_inline(self, sync_handler):
        rows = [_row(f"s{i}", i, i + 1000, "subscriber") for i in range(3)]
        rows.append(_row("g1", -500, 200, "group"))
        sync_handler.db.get_notification_messages_by_offer.return_value = rows
        with patch.object(sync_handler, "_sync_subscriber_messages_async") as async_mock:
            sync_handler.sync_offer_messages(7)
        async_mock.assert_not_called()
        assert sync_handler._edit_message_text.call_count == 4
