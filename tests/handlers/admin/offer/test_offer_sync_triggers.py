"""Step 5 tests: NotificationSender subscriber-edit branch + trigger routing."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from models.entities import NotificationMessage, Offer, OfferStatus
from notification_sender import NotificationSender


@pytest.fixture
def offer():
    return Offer(
        offer_id=5,
        name="Saison",
        description="Farmhouse",
        price_per_unit=Decimal("5.00"),
        status=OfferStatus.SOLD_OUT.value,
    )


def _row(nid, chat_id, kind):
    return NotificationMessage(notification_id=nid, offer_id=5, chat_id=chat_id, message_id=chat_id + 1, kind=kind)


class TestNotificationSenderSync:
    def _sender(self):
        s = NotificationSender(MagicMock(), 1, "test", "token")
        s._get_bot_username = MagicMock(return_value="ubbc_test_bot")
        s._t = MagicMock(side_effect=lambda key, *a, **k: key)
        s._edit_message_text = MagicMock(return_value={"success": True, "not_found": False})
        return s

    def test_edits_only_subscriber_rows(self, offer):
        s = self._sender()
        s.db.get_offer.return_value = offer
        s.db.get_notification_messages_by_offer.return_value = [
            _row("g1", -100, "group"),
            _row("s1", 10, "subscriber"),
            _row("s2", 20, "subscriber"),
        ]
        edited, failed = s.sync_subscriber_messages(offer)
        assert edited == 2
        assert failed == 0
        # Group row must not be touched here.
        edited_chats = [c.args[0] for c in s._edit_message_text.call_args_list]
        assert -100 not in edited_chats

    def test_counts_failures(self, offer):
        s = self._sender()
        s._edit_message_text.return_value = {"success": False, "not_found": True}
        s.db.get_notification_messages_by_offer.return_value = [_row("s1", 10, "subscriber")]
        edited, failed = s.sync_subscriber_messages(offer)
        assert edited == 0
        assert failed == 1
        # The Lambda has no DeleteItem permission, so it must not try to prune.
        s.db.delete_notification_message.assert_not_called()


class TestLambdaHandlerDispatch:
    def test_sync_action_calls_subscriber_sync(self, offer):
        event = {"action": "sync_offer_messages", "offer_id": 5, "environment": "test", "cancelled": True}
        with (
            patch("boto3.client") as client_mock,
            patch("notification_sender.DynamoDBService") as db_cls,
            patch.object(NotificationSender, "sync_subscriber_messages", return_value=(3, 0)) as sync_mock,
        ):
            client_mock.return_value.get_parameter.return_value = {"Parameter": {"Value": "tok"}}
            db_cls.return_value.get_offer.return_value = offer
            from notification_sender import lambda_handler

            result = lambda_handler(event, None)
        sync_mock.assert_called_once()
        assert sync_mock.call_args.kwargs["cancelled"] is True
        assert result["statusCode"] == 200

    def test_send_action_still_bulk_sends(self, offer):
        event = {"offer_id": 5, "environment": "test"}
        with (
            patch("boto3.client") as client_mock,
            patch("notification_sender.DynamoDBService") as db_cls,
            patch.object(NotificationSender, "send_bulk_notifications", return_value=(2, 0)) as bulk_mock,
        ):
            client_mock.return_value.get_parameter.return_value = {"Parameter": {"Value": "tok"}}
            db_cls.return_value.get_offer.return_value = offer
            db_cls.return_value.get_subscribers.return_value = []
            from notification_sender import lambda_handler

            lambda_handler(event, None)
        bulk_mock.assert_called_once()


class TestTriggerRouting:
    """Each trigger site must call the sync (indirectly via the wrapper or directly)."""

    def test_cancel_offer_syncs_cancelled(self):
        from handlers.admin.offer.management import OfferManagementHandler

        h = OfferManagementHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_message = MagicMock()
        h._delete_offer_boxes = MagicMock(return_value=0)
        h._notify_customer_cancellation = MagicMock()
        offer = Offer(offer_id=9, name="X", price_per_unit=Decimal("1"), status=OfferStatus.ACTIVE.value)
        h._validate_and_get_offer = MagicMock(return_value=(offer, None))
        h.db.get_orders_by_offer.return_value = []

        h.handle_confirm_cancel_offer(123, ["9"])
        h.sync_offer_messages.assert_called_once_with(9, cancelled=True)

    def test_offer_status_soldout_syncs(self):
        from handlers.admin.offer.editing import OfferEditingHandler

        h = OfferEditingHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_success = MagicMock(return_value={"status": "success"})
        offer = Offer(offer_id=9, name="X", price_per_unit=Decimal("1"), status=OfferStatus.ACTIVE.value)
        h._validate_and_get_offer = MagicMock(return_value=(offer, None))
        h.db.update_offer.return_value = True

        h.handle_offer_status(123, ["9", "soldout"])
        h.sync_offer_messages.assert_called_once_with(9)

    def test_offer_status_active_syncs(self):
        # Manual sold_out -> active must clear the marker and restore the buttons.
        from handlers.admin.offer.editing import OfferEditingHandler

        h = OfferEditingHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_success = MagicMock(return_value={"status": "success"})
        offer = Offer(offer_id=9, name="X", price_per_unit=Decimal("1"), status=OfferStatus.SOLD_OUT.value)
        h._validate_and_get_offer = MagicMock(return_value=(offer, None))
        h.db.update_offer.return_value = True

        h.handle_offer_status(123, ["9", "active"])
        h.sync_offer_messages.assert_called_once_with(9)

    def test_offer_status_completed_syncs(self):
        from handlers.admin.offer.editing import OfferEditingHandler

        h = OfferEditingHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_success = MagicMock(return_value={"status": "success"})
        offer = Offer(offer_id=9, name="X", price_per_unit=Decimal("1"), status=OfferStatus.ACTIVE.value)
        h._validate_and_get_offer = MagicMock(return_value=(offer, None))
        h.db.update_offer.return_value = True

        h.handle_offer_status(123, ["9", "completed"])
        h.sync_offer_messages.assert_called_once_with(9)

    def test_offer_status_import_does_not_sync(self):
        from handlers.admin.offer.editing import OfferEditingHandler

        h = OfferEditingHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_success = MagicMock(return_value={"status": "success"})
        offer = Offer(offer_id=9, name="X", price_per_unit=Decimal("1"), status=OfferStatus.DRAFT.value)
        h._validate_and_get_offer = MagicMock(return_value=(offer, None))
        h.db.update_offer.return_value = True

        h.handle_offer_status(123, ["9", "import"])
        h.sync_offer_messages.assert_not_called()

    def test_update_offer_name_syncs(self):
        from handlers.admin.offer.editing import OfferEditingHandler

        h = OfferEditingHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_message = MagicMock()
        h.handlers = {"info": MagicMock()}
        h.handlers["info"].handle_view_offer.return_value = {"status": "ok"}
        offer = Offer(offer_id=9, name="Old", price_per_unit=Decimal("1"), status=OfferStatus.ACTIVE.value)
        h.db.get_offer.return_value = offer
        h.db.update_offer.return_value = True

        h.handle_update_offer_name(123, ["9", "New", "Name"])
        h.sync_offer_messages.assert_called_once_with(9)

    def test_update_offer_price_syncs(self):
        from handlers.admin.offer.editing import OfferEditingHandler

        h = OfferEditingHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_message = MagicMock()
        h.handlers = {"info": MagicMock()}
        h.handlers["info"].handle_view_offer.return_value = {"status": "ok"}
        offer = Offer(offer_id=9, name="X", price_per_unit=Decimal("1"), status=OfferStatus.ACTIVE.value)
        h.db.get_offer.return_value = offer
        h.db.update_offer.return_value = True

        h.handle_update_offer_price(123, ["9", "7.50"])
        h.sync_offer_messages.assert_called_once_with(9)

    def test_update_offer_description_syncs(self):
        from handlers.admin.offer.editing import OfferEditingHandler

        h = OfferEditingHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_message = MagicMock()
        h.handlers = {"info": MagicMock()}
        h.handlers["info"].handle_view_offer.return_value = {"status": "ok"}
        offer = Offer(
            offer_id=9, name="X", description="old", price_per_unit=Decimal("1"), status=OfferStatus.ACTIVE.value
        )
        h.db.get_offer.return_value = offer
        h.db.update_offer.return_value = True

        h.handle_update_offer_description(123, ["9", "a", "new", "description"])
        h.sync_offer_messages.assert_called_once_with(9)
