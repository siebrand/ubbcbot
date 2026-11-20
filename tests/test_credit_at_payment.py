"""Credit is used once, when the delivery overview asks for the payment (audit 5, A2); against the mocked database"""

import json
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.order.order_status import OrderStatusManagement
from models.entities import AuthorizationStatus, Box, Customer, Offer, Order, OrderStatus
from services.credit_service import CreditService
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
BOX_ID = "abcdef12-0000-4000-8000-000000000000"
LINK = "https://pay.example/abc"


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    service = DynamoDBService()
    service.create_offer(
        Offer(offer_id=7, name="Pils", price_per_unit=Decimal("1.00"), wholesale_box_size=24, status="sold_out")
    )
    assert service.create_box(Box(box_id=BOX_ID, offer_id=7, max_capacity=24, current_quantity=24, status="delivered"))
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def jan(db) -> Customer:
    return db.create_customer(
        Customer(
            telegram_user_id=101,
            first_name="Jan",
            location="Utrecht",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def labeled(db, customer: Customer, euros: int) -> Order:
    """An order of ``euros`` units at €1, labeled and ready for the overview"""
    created = db.order_repo.create_order(
        Order(
            customer_id=customer.customer_id,
            box_id=BOX_ID,
            offer_id=7,
            quantity=euros,
            received_quantity=euros,
            unit_price=Decimal("1.00"),
            total_price=Decimal(euros),
            status=OrderStatus.LABELING_COMPLETED.value,
        )
    )
    assert created
    return created


def balance(db, customer: Customer) -> Decimal:
    return CreditService(db).get_customer_credit_balance(customer.customer_id)


def give(db, customer: Customer, amount: str) -> None:
    assert CreditService(db).issue_credit(customer.customer_id, Decimal(amount), "Start", ADMIN_ID)


def overview(db) -> str:
    """Send the overviews; the payment message the customer gets"""
    handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler.lambda_client = Mock()
    handler.start_send_overviews(ADMIN_ID)
    handler.handle_payment_link_input(ADMIN_ID, LINK, db.get_edit_context_by_chat_id(ADMIN_ID).entity_id)
    (message,) = json.loads(handler.lambda_client.invoke.call_args.kwargs["Payload"])["messages"]
    return message["message"]


def reminder(db, customer: Customer) -> str:
    handler = OrderStatusManagement(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._send_user_message = Mock(return_value={"success": True})
    with patch.object(handler, "handle_send_payment_reminder"):
        handler.handle_send_payment_reminder_to_customer(ADMIN_ID, customer.customer_id)
    return handler._send_user_message.call_args.args[1]


def to_pay_line(db, customer: Customer, amount: str) -> str:
    handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
    return handler._t("amount_to_pay_bold", customer.telegram_user_id, total=Decimal(amount))


class TestTheBalanceAndWhatIsToPay:
    def test_credit_larger_than_the_delivery_leaves_nothing_to_pay_and_the_rest_of_the_credit(self, db, jan):
        """The owner's case: credit 10, a delivery of 5 → 0 to pay, credit 5"""
        give(db, jan, "10")
        labeled(db, jan, 5)

        message = overview(db)

        assert balance(db, jan) == Decimal("5")
        assert to_pay_line(db, jan, "0") in message
        assert LINK not in message
        handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
        assert handler._t("nothing_to_pay", 101) in message

    def test_credit_smaller_than_the_delivery_is_used_up(self, db, jan):
        give(db, jan, "5")
        labeled(db, jan, 12)

        message = overview(db)

        assert balance(db, jan) == Decimal("0")
        assert to_pay_line(db, jan, "7") in message
        assert LINK in message

    def test_credit_equal_to_the_delivery(self, db, jan):
        give(db, jan, "12")
        labeled(db, jan, 12)

        message = overview(db)

        assert balance(db, jan) == Decimal("0")
        assert to_pay_line(db, jan, "0") in message

    def test_a_debt_is_added_to_the_payment(self, db, jan):
        assert CreditService(db).issue_credit(jan.customer_id, Decimal("-3"), "Broken bottle", ADMIN_ID)
        labeled(db, jan, 12)

        message = overview(db)

        assert balance(db, jan) == Decimal("0")
        assert to_pay_line(db, jan, "15") in message

    def test_without_credit_the_whole_delivery_is_to_pay_and_nothing_is_booked(self, db, jan):
        labeled(db, jan, 12)

        message = overview(db)

        # Without credit the total is what is to pay: no separate line for it
        handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
        assert handler._t("total_amount_bold", 101, total=Decimal("12")) in message
        assert to_pay_line(db, jan, "12") not in message
        assert db.get_all_credit_transactions_by_customer(jan.customer_id) == []

    def test_credit_spread_over_several_orders_adds_up(self, db, jan):
        give(db, jan, "6")
        labeled(db, jan, 4), labeled(db, jan, 4)

        overview(db)

        orders = db.get_orders_by_customer(jan.customer_id)
        assert sum(o.credit_applied for o in orders) == Decimal("6")
        assert all(o.credit_applied <= o.total_price for o in orders)
        assert balance(db, jan) == Decimal("0")


class TestAppliedOnce:
    def test_the_reminder_asks_the_same_and_does_not_use_credit_again(self, db, jan):
        give(db, jan, "5")
        labeled(db, jan, 12)
        overview(db)
        give(db, jan, "4")  # new credit after the overview is for the next delivery

        message = reminder(db, jan)

        assert to_pay_line(db, jan, "7") in message
        assert balance(db, jan) == Decimal("4")

    def test_credit_already_applied_to_an_order_is_not_applied_again(self, db, jan):
        give(db, jan, "5")
        order = labeled(db, jan, 12)
        overview(db)
        give(db, jan, "5")
        awaiting = db.get_order(order.order_id)

        result = CreditService(db).apply_credit_to_orders(jan.customer_id, [awaiting])

        assert result["credit_applied"] == Decimal("0")
        assert balance(db, jan) == Decimal("5")
        assert db.get_order(order.order_id).credit_applied == Decimal("5")

    def test_the_admin_lists_show_what_is_to_pay(self, db, jan):
        give(db, jan, "5")
        labeled(db, jan, 12)
        overview(db)
        handler = OrderStatusManagement(db, ADMIN_ID, "prod", "token")
        handler._send_message = Mock(return_value={"success": True})

        handler.handle_process_payment(ADMIN_ID, [])
        handler.handle_send_payment_reminder(ADMIN_ID, [])

        buttons = [
            b["text"]
            for c in handler._send_message.call_args_list
            for row in c.kwargs["reply_markup"]["inline_keyboard"]
            for b in row
        ]
        assert any("€7.00" in text for text in buttons)
        assert not any("€12.00" in text for text in buttons)

    def test_the_payment_received_is_the_amount_that_was_to_pay(self, db, jan):
        give(db, jan, "5")
        labeled(db, jan, 12)
        overview(db)
        handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
        handler._send_message = Mock(return_value={"success": True})
        handler.lambda_client = Mock()

        with patch("handlers.admin.order_commands.AdminOrderCommands"):
            handler.handle_process_customer_paid(ADMIN_ID, jan.customer_id)

        (message,) = json.loads(handler.lambda_client.invoke.call_args.kwargs["Payload"])["messages"]
        assert "€7.00" in message["message"]
        assert "€12.00" not in message["message"]
