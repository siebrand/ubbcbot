"""Export expiry: exports sent to the admin are tracked and deleted after an hour, event-based."""

import logging
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from handlers.admin.import_handler import ImportHandler
from handlers.admin.offer import OfferCommands
from handlers.admin.order.order_viewing import OrderViewing
from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus, Customer, NotificationMessage, Offer, Order, OrderStatus
from services.bot_service import BotService
from services.database import DynamoDBService
from services.export_expiry import (
    EXPORT_KIND,
    EXPORT_LIFETIME_SECONDS,
    EXPORT_OFFER_ID,
    ROW_GRACE_SECONDS,
    SWEEP_INTERVAL_SECONDS,
    ExportExpiryService,
)
from services.user_cache import UserCache

ADMIN_ID = 15005473
GROUP_ID = -1003399818858
NOW = 1_800_000_000
OK = {"success": True, "gone": False}
GONE = {"success": False, "gone": True}
TRANSIENT = {"success": False, "gone": False}


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def reset_throttle():
    ExportExpiryService._last_sweep = 0.0
    yield
    ExportExpiryService._last_sweep = 0.0


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def delete():
    return Mock(return_value=OK)


@pytest.fixture
def service(db, delete, clock):
    return ExportExpiryService(db, delete, clock)


def _rows(db):
    return db.get_notification_messages_by_offer(EXPORT_OFFER_ID)


class TestTrack:
    def test_stores_an_export_row_with_expiry(self, service, db):
        assert service.track(ADMIN_ID, 555)

        (row,) = _rows(db)
        assert row.kind == EXPORT_KIND
        assert row.offer_id == EXPORT_OFFER_ID
        assert (row.chat_id, row.message_id) == (ADMIN_ID, 555)
        assert row.expires_at == NOW + EXPORT_LIFETIME_SECONDS

    def test_tracking_row_outlives_the_message_deadline(self, service, db):
        service.track(ADMIN_ID, 555)

        (row,) = _rows(db)
        assert row.ttl == row.expires_at + ROW_GRACE_SECONDS

    def test_lifetime_is_one_hour(self):
        assert EXPORT_LIFETIME_SECONDS == 3600


class TestSweep:
    def test_nothing_happens_before_expiry(self, service, db, delete, clock):
        service.track(ADMIN_ID, 555)
        clock.now = NOW + EXPORT_LIFETIME_SECONDS - 1

        assert service.sweep(force=True) == 0

        delete.assert_not_called()
        assert len(_rows(db)) == 1

    def test_deletes_the_message_and_row_after_expiry(self, service, db, delete, clock):
        service.track(ADMIN_ID, 555)
        clock.now = NOW + EXPORT_LIFETIME_SECONDS

        assert service.sweep(force=True) == 1

        delete.assert_called_once_with(ADMIN_ID, 555)
        assert _rows(db) == []

    def test_only_expired_exports_are_deleted(self, service, db, delete, clock):
        service.track(ADMIN_ID, 1)
        clock.now = NOW + 1800
        service.track(ADMIN_ID, 2)
        clock.now = NOW + EXPORT_LIFETIME_SECONDS + 10

        assert service.sweep(force=True) == 1

        delete.assert_called_once_with(ADMIN_ID, 1)
        assert [r.message_id for r in _rows(db)] == [2]

    def test_message_already_gone_drops_the_row(self, service, db, delete, clock, caplog):
        delete.return_value = GONE
        service.track(ADMIN_ID, 555)
        clock.now = NOW + EXPORT_LIFETIME_SECONDS

        with caplog.at_level(logging.WARNING):
            assert service.sweep(force=True) == 1

        assert _rows(db) == []
        assert "555" in caplog.text

    def test_transient_failure_keeps_the_row_and_retries(self, service, db, delete, clock):
        delete.return_value = TRANSIENT
        service.track(ADMIN_ID, 555)
        clock.now = NOW + EXPORT_LIFETIME_SECONDS

        assert service.sweep(force=True) == 0
        assert len(_rows(db)) == 1

        delete.return_value = OK
        assert service.sweep(force=True) == 1
        assert _rows(db) == []

    def test_other_notification_rows_are_left_alone(self, service, db, delete, clock):
        db.create_notification_message(NotificationMessage(offer_id=5, chat_id=GROUP_ID, message_id=9, kind="group"))
        db.create_notification_message(
            NotificationMessage(offer_id=EXPORT_OFFER_ID, chat_id=1, message_id=8, kind="group", expires_at=NOW - 10)
        )
        clock.now = NOW + 10 * EXPORT_LIFETIME_SECONDS

        assert service.sweep(force=True) == 0

        delete.assert_not_called()
        assert len(db.get_notification_messages_by_offer(5)) == 1

    def test_rows_without_expiry_are_ignored(self, service, db, delete):
        db.create_notification_message(
            NotificationMessage(offer_id=EXPORT_OFFER_ID, chat_id=1, message_id=8, kind=EXPORT_KIND)
        )

        assert service.sweep(force=True) == 0
        delete.assert_not_called()

    def test_database_errors_never_propagate(self, delete, clock):
        broken = Mock()
        broken.get_notification_messages_by_offer.side_effect = RuntimeError("boom")

        assert ExportExpiryService(broken, delete, clock).sweep(force=True) == 0


class TestThrottle:
    def test_repeated_sweeps_within_the_interval_are_skipped(self, service, db, delete, clock):
        service.track(ADMIN_ID, 555)
        clock.now = NOW + EXPORT_LIFETIME_SECONDS
        assert service.sweep() == 1
        service.track(ADMIN_ID, 556)
        clock.now += EXPORT_LIFETIME_SECONDS  # 556 is expired now, but the previous sweep was just a moment ago
        ExportExpiryService._last_sweep = clock.now - (SWEEP_INTERVAL_SECONDS - 1)

        assert service.sweep() == 0

        assert len(_rows(db)) == 1

    def test_sweep_runs_again_after_the_interval(self, service, db, clock):
        service.track(ADMIN_ID, 555)
        clock.now = NOW + EXPORT_LIFETIME_SECONDS
        ExportExpiryService._last_sweep = clock.now - SWEEP_INTERVAL_SECONDS

        assert service.sweep() == 1

    def test_force_ignores_the_throttle(self, service, clock):
        service.track(ADMIN_ID, 555)
        clock.now = NOW + EXPORT_LIFETIME_SECONDS
        ExportExpiryService._last_sweep = clock.now

        assert service.sweep(force=True) == 1


def _response(status, text=""):
    response = Mock(status_code=status, text=text)
    response.json.return_value = {"result": {"message_id": 321}}
    return response


class TestTelegramHelpers:
    @pytest.fixture
    def handler(self):
        return BaseHandler(Mock(), ADMIN_ID, "test", "token")

    def test_delete_success(self, handler):
        with patch("services.telegram_client.requests.post", return_value=_response(200)):
            assert handler._delete_message_result(1, 2) == OK

    @pytest.mark.parametrize(
        "body",
        [
            "Bad Request: message to delete not found",
            "Bad Request: message can't be deleted",
            "Bad Request: chat not found",
        ],
    )
    def test_delete_of_a_message_that_is_gone_is_final(self, handler, body):
        with patch("services.telegram_client.requests.post", return_value=_response(400, body)):
            assert handler._delete_message_result(1, 2) == GONE

    @pytest.mark.parametrize("status", [429, 500, 502])
    def test_server_side_errors_are_retryable(self, handler, status):
        with patch("services.telegram_client.requests.post", return_value=_response(status, "try later")):
            assert handler._delete_message_result(1, 2) == TRANSIENT

    def test_network_errors_are_retryable(self, handler):
        with patch("services.telegram_client.requests.post", side_effect=OSError("down")):
            assert handler._delete_message_result(1, 2) == TRANSIENT

    def test_send_document_message_returns_the_message_id(self, handler):
        with patch("services.telegram_client.requests.post", return_value=_response(200)) as post:
            result = handler._send_document_message(ADMIN_ID, "a,b", "x.csv", "caption")

        assert result == {"success": True, "message_id": 321}
        assert post.call_args.kwargs["data"]["caption"] == "TEST - caption"

    def test_send_document_message_failure(self, handler):
        with patch("services.telegram_client.requests.post", return_value=_response(400, "nope")):
            assert handler._send_document_message(ADMIN_ID, "a,b", "x.csv") == {"success": False}

    def test_send_document_keeps_returning_a_bool(self, handler):
        with patch("services.telegram_client.requests.post", return_value=_response(200)):
            assert handler._send_document(ADMIN_ID, "a,b", "x.csv") is True
        with patch("services.telegram_client.requests.post", return_value=_response(500)):
            assert handler._send_document(ADMIN_ID, "a,b", "x.csv") is False


class TestExportFlow:
    @pytest.fixture
    def handler(self, db):
        customer = db.create_customer(
            Customer(
                telegram_user_id=4242,
                first_name="Jantje",
                last_name="Beton",
                authorization_status=AuthorizationStatus.APPROVED.value,
            )
        )
        db.create_offer(Offer(offer_id=7, name="Pils", price_per_unit=Decimal("2.50")))
        db.order_repo.create_order(
            Order(
                customer_id=customer.customer_id,
                offer_id=7,
                quantity=2,
                unit_price=Decimal("2.50"),
                total_price=Decimal("5.00"),
                status=OrderStatus.PENDING.value,
            )
        )
        handler = OrderViewing(db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        handler._send_document_message = Mock(return_value={"success": True, "message_id": 777})
        handler.export_expiry._delete_message = Mock(return_value=OK)
        return handler

    def test_export_goes_to_the_admin_private_chat_even_when_asked_in_a_group(self, handler, db):
        result = handler._export_orders_by_status(GROUP_ID, "active")

        assert result == {"status": "success"}
        assert handler._send_document_message.call_args.args[0] == ADMIN_ID
        group_texts = [c.args[1] for c in handler._send_message.call_args_list if c.args[0] == GROUP_ID]
        assert len(group_texts) == 1  # only the "sent privately" note, never the data

    def test_export_requested_in_the_private_chat_sends_no_extra_message(self, handler):
        handler._export_orders_by_status(ADMIN_ID, "active")

        handler._send_message.assert_not_called()

    def test_export_is_tracked_for_expiry(self, handler, db):
        handler._export_orders_by_status(ADMIN_ID, "active")

        (row,) = _rows(db)
        assert (row.chat_id, row.message_id, row.kind) == (ADMIN_ID, 777, EXPORT_KIND)

    def test_caption_announces_the_expiry(self, handler):
        handler._export_orders_by_status(ADMIN_ID, "active")

        caption = handler._send_document_message.call_args.args[3]
        assert "60" in caption

    def test_full_export_is_also_private_and_tracked(self, handler, db):
        handler._export_orders_by_status(GROUP_ID, "full")

        assert handler._send_document_message.call_args.args[0] == ADMIN_ID
        assert len(_rows(db)) == 1

    def test_failed_send_reports_an_error_and_tracks_nothing(self, handler, db):
        handler._send_document_message.return_value = {"success": False}

        result = handler._export_orders_by_status(GROUP_ID, "active")

        assert result == {"status": "error"}
        assert _rows(db) == []
        assert handler._send_message.call_args.args[0] == GROUP_ID

    def test_nothing_to_export_sends_no_file_and_tracks_nothing(self, handler, db):
        handler._export_orders_by_status(ADMIN_ID, "cancelled")

        handler._send_document_message.assert_not_called()
        assert _rows(db) == []

    def test_an_expired_export_is_cleared_when_a_new_one_is_made(self, handler, db):
        db.create_notification_message(
            NotificationMessage(
                offer_id=EXPORT_OFFER_ID,
                chat_id=ADMIN_ID,
                message_id=111,
                kind=EXPORT_KIND,
                expires_at=1,
                ttl=NOW,
            )
        )

        handler._export_orders_by_status(ADMIN_ID, "active")

        handler.export_expiry._delete_message.assert_called_once_with(ADMIN_ID, 111)
        assert [r.message_id for r in _rows(db)] == [777]


class TestTriggers:
    @pytest.fixture
    def bot(self):
        bot = BotService.__new__(BotService)
        bot.admin_user_id = ADMIN_ID
        bot.base_handler = Mock()
        return bot

    def test_admin_message_triggers_a_sweep(self, bot):
        bot._expire_exports_on_admin_update({"message": {"from": {"id": ADMIN_ID}, "text": "hi"}})

        bot.base_handler.expire_exports.assert_called_once_with()

    def test_admin_button_press_triggers_a_sweep(self, bot):
        bot._expire_exports_on_admin_update({"callback_query": {"from": {"id": ADMIN_ID}, "data": "x"}})

        bot.base_handler.expire_exports.assert_called_once_with()

    def test_customer_updates_do_not_trigger_a_sweep(self, bot):
        bot._expire_exports_on_admin_update({"message": {"from": {"id": 999}, "text": "hi"}})
        bot._expire_exports_on_admin_update({"callback_query": {"from": {"id": 999}, "data": "x"}})
        bot._expire_exports_on_admin_update({"edited_message": {}})

        bot.base_handler.expire_exports.assert_not_called()

    def test_a_failing_sweep_never_breaks_update_handling(self, bot):
        bot.base_handler.expire_exports.side_effect = RuntimeError("boom")

        bot._expire_exports_on_admin_update({"message": {"from": {"id": ADMIN_ID}}})

    def test_process_update_sweeps_for_the_admin(self, bot):
        bot.db = Mock()
        bot.db.mark_update_processed.return_value = True
        bot.callback_handler = Mock()

        bot.process_update({"update_id": 1, "callback_query": {"from": {"id": ADMIN_ID}, "data": "x"}})

        bot.base_handler.expire_exports.assert_called_once_with()

    def test_offer_message_sync_triggers_a_sweep(self):
        db = Mock()
        db.get_offer.return_value = Offer(offer_id=1, name="Pils")
        db.get_notification_messages_by_offer.return_value = []
        handler = BaseHandler(db, ADMIN_ID, "test", "token")
        handler.expire_exports = Mock()
        handler._get_bot_username = Mock(return_value="ubbc_test_bot")

        handler.sync_offer_messages(1)

        handler.expire_exports.assert_called_once_with()

    def test_publishing_an_offer_triggers_a_sweep(self):
        handler = OfferCommands(Mock(), ADMIN_ID, "test", "token")
        handler.expire_exports = Mock()
        handler._send_rich_offer_message = Mock()
        handler._notify_subscribers_rich = Mock()

        handler._announce_offer(Offer(offer_id=1, name="Pils"))

        handler.expire_exports.assert_called_once_with()

    def test_announcing_an_imported_offer_triggers_a_sweep(self):
        handler = ImportHandler(Mock(), ADMIN_ID, "test", "token")
        handler.expire_exports = Mock()
        handler._send_rich_offer_message = Mock()
        handler._notify_subscribers_rich = Mock()

        handler._announce_offer(Offer(offer_id=1, name="Pils"))

        handler.expire_exports.assert_called_once_with()

    def test_expire_exports_never_raises(self):
        handler = BaseHandler(Mock(), ADMIN_ID, "test", "token")
        handler.export_expiry = Mock()
        handler.export_expiry.sweep.side_effect = RuntimeError("boom")

        handler.expire_exports()
