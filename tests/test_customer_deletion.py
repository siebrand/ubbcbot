"""Customer deletion (/delete_user): blockers, confirmation flow, data retention and authorization."""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.user_commands import UserCommands
from models.entities import (
    AuthorizationStatus,
    CreditTransaction,
    Customer,
    CustomerCredit,
    Offer,
    Order,
    OrderHistory,
    OrderStatus,
)
from services.callback_handler import CallbackHandler
from services.command_router import CommandRouter
from services.customer_deletion import CustomerDeletionService
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
CHAT_ID = 15005473

OPEN_STATUSES = [
    OrderStatus.PENDING,
    OrderStatus.ORDERED,
    OrderStatus.RECEIVED_PARTIAL_DELAYED,
    OrderStatus.READY_FOR_LABELING,
    OrderStatus.LABELING_COMPLETED,
    OrderStatus.AWAITING_PAYMENT,
]
SETTLED_STATUSES = [OrderStatus.COMPLETED, OrderStatus.CANCELLED]


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def offer(db):
    offer = Offer(offer_id=7, name="Pils & Co", price_per_unit=Decimal("2.50"))
    assert db.create_offer(offer)
    return offer


@pytest.fixture
def customer(db):
    created = db.create_customer(
        Customer(
            telegram_user_id=4242,
            username="jantje",
            first_name="Jantje",
            last_name="Beton",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )
    assert created
    return created


def _order(db, customer, offer, status):
    order = Order(
        customer_id=customer.customer_id,
        offer_id=offer.offer_id,
        quantity=2,
        unit_price=Decimal("2.50"),
        total_price=Decimal("5.00"),
        status=status.value,
    )
    assert db.order_repo.create_order(order)
    return order


def _credit(db, customer, balance):
    assert db.create_customer_credit(CustomerCredit(customer_id=customer.customer_id, current_balance=balance))


@pytest.fixture
def handler(db):
    handler = UserCommands(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    return handler


def _sent_text(handler) -> str:
    return handler._send_message.call_args.args[1]


def _sent_callbacks(handler) -> list[str]:
    markup = handler._send_message.call_args.kwargs.get("reply_markup") or {}
    return [b["callback_data"] for row in markup.get("inline_keyboard", []) for b in row]


class TestDeletionBlockers:
    @pytest.mark.parametrize("status", OPEN_STATUSES, ids=lambda s: s.value)
    def test_open_order_blocks(self, db, customer, offer, status):
        order = _order(db, customer, offer, status)

        blockers = CustomerDeletionService(db).get_blockers(customer)

        assert blockers.blocked
        assert [o.order_id for o in blockers.open_orders] == [order.order_id]

    @pytest.mark.parametrize("status", SETTLED_STATUSES, ids=lambda s: s.value)
    def test_settled_order_does_not_block(self, db, customer, offer, status):
        _order(db, customer, offer, status)

        assert not CustomerDeletionService(db).get_blockers(customer).blocked

    @pytest.mark.parametrize("balance", [Decimal("12.50"), Decimal("-3.00")])
    def test_non_zero_credit_balance_blocks(self, db, customer, balance):
        _credit(db, customer, balance)

        blockers = CustomerDeletionService(db).get_blockers(customer)

        assert blockers.blocked
        assert blockers.credit_balance == balance

    def test_zero_credit_balance_does_not_block(self, db, customer):
        _credit(db, customer, Decimal("0.00"))

        assert not CustomerDeletionService(db).get_blockers(customer).blocked

    def test_only_this_customers_orders_count(self, db, customer, offer):
        other = db.create_customer(Customer(telegram_user_id=1, first_name="Other"))
        _order(db, other, offer, OrderStatus.AWAITING_PAYMENT)

        assert not CustomerDeletionService(db).get_blockers(customer).blocked


class TestDeleteCustomer:
    def test_removes_the_customer_row_and_clears_caches(self, db, customer):
        assert db.get_customer_by_telegram_id(4242) is not None  # warm the cache

        deleted, _ = CustomerDeletionService(db).delete(customer)

        assert deleted
        assert db.get_customer(customer.customer_id) is None
        assert db.get_customer_by_telegram_id(4242) is None
        assert customer.customer_id not in [c.customer_id for c in db.customer_repo.get_all_customers()]
        assert customer.customer_id not in [c.customer_id for c in db.get_subscribers()]

    def test_returning_user_registers_as_a_new_customer(self, db, customer):
        CustomerDeletionService(db).delete(customer)

        again = db.create_customer(Customer(telegram_user_id=4242, first_name="Jantje"))

        assert again.customer_id != customer.customer_id
        assert again.authorization_status == AuthorizationStatus.UNAUTHORIZED.value

    def test_blocked_customer_is_not_deleted(self, db, customer, offer):
        _order(db, customer, offer, OrderStatus.AWAITING_PAYMENT)

        deleted, blockers = CustomerDeletionService(db).delete(customer)

        assert not deleted
        assert blockers.blocked
        assert db.get_customer(customer.customer_id) is not None

    def test_deleting_a_missing_customer_returns_false(self, db):
        assert db.delete_customer("does-not-exist") is False

    def test_orders_credit_transactions_and_history_are_kept(self, db, customer, offer):
        order = _order(db, customer, offer, OrderStatus.COMPLETED)
        _credit(db, customer, Decimal("0.00"))
        transaction = CreditTransaction(
            customer_id=customer.customer_id,
            transaction_type="ADJUSTMENT",
            amount=Decimal("5.00"),
            created_by=ADMIN_ID,
        )
        assert db.create_credit_transaction(transaction)
        history = OrderHistory(
            customer_id=customer.customer_id,
            offer_name=offer.name,
            event_type="PAYMENT_RECEIVED",
            amount=Decimal("5.00"),
        )
        assert db.create_order_history(history)

        deleted, _ = CustomerDeletionService(db).delete(customer)

        assert deleted
        assert [o.order_id for o in db.get_orders_by_customer(customer.customer_id)] == [order.order_id]
        assert len(db.get_credit_transactions_by_customer(customer.customer_id)) == 1
        stored = db.order_history_table.get_item(Key={"history_id": history.history_id}).get("Item")
        assert stored is not None
        assert stored["customer_id"] == customer.customer_id
        assert "first_name" not in stored


class TestDeleteUserCommand:
    def test_without_arguments_shows_usage(self, handler):
        result = handler.handle_delete_user(CHAT_ID, [])

        assert result == {"status": "invalid_args"}
        assert "/delete_user" in _sent_text(handler)

    def test_unknown_user_reports_not_found(self, handler, customer):
        result = handler.handle_delete_user(CHAT_ID, ["nobody-like-this"])

        assert result["status"] == "user_not_found"

    def test_asks_for_confirmation_without_deleting(self, handler, db, customer):
        result = handler.handle_delete_user(CHAT_ID, ["jantje"])

        assert result == {"status": "confirmation_required"}
        assert f"delete_user_confirm_{customer.customer_id}" in _sent_callbacks(handler)
        assert "cancel_confirmation" in _sent_callbacks(handler)
        assert db.get_customer(customer.customer_id) is not None

    def test_resolves_a_partial_customer_id(self, handler, customer):
        result = handler.handle_delete_user(CHAT_ID, [customer.customer_id[:8]])

        assert result == {"status": "confirmation_required"}

    def test_open_order_blocks_and_lists_the_order(self, handler, db, customer, offer):
        order = _order(db, customer, offer, OrderStatus.AWAITING_PAYMENT)

        result = handler.handle_delete_user(CHAT_ID, ["jantje"])

        assert result == {"status": "delete_blocked"}
        text = _sent_text(handler)
        assert order.order_id[:8] in text
        assert "awaiting_payment" in text
        assert "Pils &amp; Co" in text  # offer name is HTML-escaped
        assert _sent_callbacks(handler) == []  # no confirm button
        assert db.get_customer(customer.customer_id) is not None

    def test_credit_balance_blocks_and_shows_the_amount(self, handler, db, customer):
        _credit(db, customer, Decimal("12.50"))

        result = handler.handle_delete_user(CHAT_ID, ["jantje"])

        assert result == {"status": "delete_blocked"}
        assert "12.50" in _sent_text(handler)
        assert _sent_callbacks(handler) == []

    def test_open_order_and_credit_are_both_reported(self, handler, db, customer, offer):
        order = _order(db, customer, offer, OrderStatus.PENDING)
        _credit(db, customer, Decimal("-4.00"))

        handler.handle_delete_user(CHAT_ID, ["jantje"])

        text = _sent_text(handler)
        assert order.order_id[:8] in text
        assert "-4.00" in text

    def test_names_are_html_escaped(self, handler, db):
        db.create_customer(Customer(telegram_user_id=77, first_name="<b>Evil</b>", last_name="&"))

        handler.handle_delete_user(CHAT_ID, ["Evil"])

        text = _sent_text(handler)
        assert "<b>Evil</b>" not in text
        assert "&lt;b&gt;Evil&lt;/b&gt;" in text
        assert handler._send_message.call_args.kwargs["parse_mode"] == "HTML"

    def test_ambiguous_name_shows_disambiguation_that_leads_to_confirmation(self, handler, db, customer):
        other = db.create_customer(Customer(telegram_user_id=4343, first_name="Jantje", last_name="Steen"))

        result = handler.handle_delete_user(CHAT_ID, ["jantje"])

        assert result["status"] == "disambiguation_shown"
        callbacks = _sent_callbacks(handler)
        assert f"delete_user_select_{customer.customer_id}" in callbacks
        assert f"delete_user_select_{other.customer_id}" in callbacks

        result = handler.handle_delete_user_select(CHAT_ID, other.customer_id)

        assert result == {"status": "confirmation_required"}
        assert f"delete_user_confirm_{other.customer_id}" in _sent_callbacks(handler)

    def test_select_of_a_blocked_customer_is_blocked(self, handler, db, customer, offer):
        _order(db, customer, offer, OrderStatus.ORDERED)

        result = handler.handle_delete_user_select(CHAT_ID, customer.customer_id)

        assert result == {"status": "delete_blocked"}


class TestDeleteUserConfirm:
    def test_deletes_the_customer(self, handler, db, customer):
        result = handler.handle_delete_user_confirm(CHAT_ID, customer.customer_id)

        assert result == {"status": "success"}
        assert db.get_customer(customer.customer_id) is None
        assert "Jantje Beton" in _sent_text(handler)

    def test_rechecks_blockers_at_confirmation_time(self, handler, db, customer, offer):
        # The prompt was shown while the customer had nothing outstanding; an order arrived since.
        handler.handle_delete_user(CHAT_ID, ["jantje"])
        _order(db, customer, offer, OrderStatus.PENDING)

        result = handler.handle_delete_user_confirm(CHAT_ID, customer.customer_id)

        assert result == {"status": "delete_blocked"}
        assert db.get_customer(customer.customer_id) is not None

    def test_pressing_confirm_twice_reports_not_found(self, handler, customer):
        handler.handle_delete_user_confirm(CHAT_ID, customer.customer_id)

        result = handler.handle_delete_user_confirm(CHAT_ID, customer.customer_id)

        assert result["status"] == "user_not_found"

    def test_delete_failure_is_reported(self, handler, db, customer):
        db.delete_customer = Mock(return_value=False)

        result = handler.handle_delete_user_confirm(CHAT_ID, customer.customer_id)

        assert result == {"status": "error"}
        assert db.get_customer(customer.customer_id) is not None

    def test_deletion_log_contains_the_id_but_no_name(self, handler, customer, caplog):
        import logging

        caplog.set_level(logging.INFO)

        handler.handle_delete_user_confirm(CHAT_ID, customer.customer_id)

        logs = "\n".join(r.getMessage() for r in caplog.records)
        assert customer.customer_id in logs
        assert "Jantje" not in logs
        assert "jantje" not in logs


class TestAuthorizationAndRouting:
    def test_customer_callbacks_never_match_the_delete_callbacks(self):
        callbacks = CallbackHandler(Mock(), 1, "test", "token", handlers={}, media_handler=Mock())
        for data in ("delete_user_confirm_abc", "delete_user_select_abc"):
            assert not callbacks.customer_callback(data)

    @pytest.mark.parametrize(
        "data, method",
        [
            ("delete_user_confirm_abc-123", "handle_delete_user_confirm"),
            ("delete_user_select_abc-123", "handle_delete_user_select"),
        ],
    )
    def test_admin_callbacks_route_to_the_handler(self, data, method):
        handlers = {name: Mock() for name in ("user", "admin_commands", "admin_order", "credit")}
        callback_handler = CallbackHandler(Mock(), ADMIN_ID, "test", "token", handlers, Mock())
        query = {
            "id": "q",
            "from": {"id": ADMIN_ID},
            "message": {"chat": {"id": CHAT_ID}, "message_id": 1},
            "data": data,
        }

        callback_handler.handle_callback_query(query)

        getattr(handlers["user"], method).assert_called_once_with(CHAT_ID, "abc-123")

    def test_non_admin_cannot_trigger_the_delete_callback(self):
        handlers = {name: Mock() for name in ("user", "admin_commands", "admin_order", "credit")}
        db = Mock()
        db.get_customer_by_telegram_id.return_value = Mock(authorization_status="approved", language="nl")
        callback_handler = CallbackHandler(db, ADMIN_ID, "test", "token", handlers, Mock())
        callback_handler._send_message = Mock()
        query = {
            "id": "q",
            "from": {"id": 999},
            "message": {"chat": {"id": 999}, "message_id": 1},
            "data": "delete_user_confirm_abc-123",
        }

        callback_handler.handle_callback_query(query)

        handlers["user"].handle_delete_user_confirm.assert_not_called()

    def _router(self, approved_customer=True):
        db = Mock()
        db.get_customer_by_telegram_id.return_value = Mock(authorization_status="approved", language="nl")
        handlers = {"user": Mock(), "info": Mock(), "auth": Mock()}
        return CommandRouter(db, ADMIN_ID, "test", handlers), handlers

    def test_admin_command_is_routed(self):
        router, handlers = self._router()

        router.route_command(CHAT_ID, ADMIN_ID, "/delete_user jantje beton")

        handlers["user"].handle_delete_user.assert_called_once_with(CHAT_ID, ["jantje", "beton"])

    def test_non_admin_command_is_not_routed(self):
        router, handlers = self._router()
        router.base_handler._send_message = Mock()

        router.route_command(999, 999, "/delete_user jantje")

        handlers["user"].handle_delete_user.assert_not_called()
