"""From the delivery overview to the payment message, against the (mocked) database"""

import json
from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.order.order_status import OrderStatusManagement
from handlers.customer.order_commands import CustomerOrderCommands
from models.entities import AuthorizationStatus, Box, Customer, Offer, Order, OrderStatus
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
        Offer(offer_id=7, name="Pils", price_per_unit=Decimal("2.50"), wholesale_box_size=6, status="sold_out")
    )
    assert service.create_box(Box(box_id=BOX_ID, offer_id=7, max_capacity=6, current_quantity=6, status="delivered"))
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


def labeled(db, customer: Customer, quantity: int) -> Order:
    created = db.order_repo.create_order(
        Order(
            customer_id=customer.customer_id,
            box_id=BOX_ID,
            offer_id=7,
            quantity=quantity,
            received_quantity=quantity,
            unit_price=Decimal("2.50"),
            total_price=Decimal("2.50") * quantity,
            status=OrderStatus.LABELING_COMPLETED.value,
        )
    )
    assert created
    return created


@pytest.fixture
def handler(db):
    handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler.lambda_client = Mock()
    return handler


def start_and_reply(handler, db, between=lambda: None, link: str = LINK) -> list[dict]:
    """Start the overviews, let something happen, reply with the link; the messages handed to the sender"""
    handler.start_send_overviews(ADMIN_ID)
    context = db.get_edit_context_by_chat_id(ADMIN_ID)
    between()
    handler.handle_payment_link_input(ADMIN_ID, link, context.entity_id)
    if not handler.lambda_client.invoke.called:
        return []
    return json.loads(handler.lambda_client.invoke.call_args.kwargs["Payload"])["messages"]


class TestThePaymentLink:
    def test_the_link_is_escaped_in_the_html_message(self, handler, db, jan):
        labeled(db, jan, 4)

        (message,) = start_and_reply(handler, db, link="https://pay.example/r?a=1&b=<2>")

        assert "https://pay.example/r?a=1&amp;b=&lt;2&gt;" in message["message"]
        assert "&b=<2>" not in message["message"]

    @pytest.mark.parametrize("link", ["not a link", "http://pay.example/abc", "https://pay.example/a b", ""])
    def test_what_is_not_an_https_link_is_refused_and_asked_again(self, handler, db, jan, link):
        order = labeled(db, jan, 4)

        assert start_and_reply(handler, db, link=link) == []

        assert db.get_order(order.order_id).status == OrderStatus.LABELING_COMPLETED.value
        texts = [c.args[1] for c in handler._send_message.call_args_list]
        assert handler._t("invalid_payment_link", ADMIN_ID) in texts
        assert db.get_edit_context_by_chat_id(ADMIN_ID).edit_type == "payment_link_input"


class TestOnlyReadyOrdersMove:
    def test_an_order_cancelled_in_between_is_not_charged_or_listed(self, handler, db, jan):
        kept, cancelled = labeled(db, jan, 4), labeled(db, jan, 2)

        def cancel():
            assert db.update_order(cancelled.order_id, {"status": OrderStatus.CANCELLED.value})

        (message,) = start_and_reply(handler, db, between=cancel)

        assert db.get_order(cancelled.order_id).status == OrderStatus.CANCELLED.value
        assert db.get_order(kept.order_id).status == OrderStatus.AWAITING_PAYMENT.value
        assert "4x [7] Pils — €10.00" in message["message"]
        assert "€15.00" not in message["message"]

    def test_a_customer_with_nothing_left_to_pay_gets_no_message(self, handler, db, jan):
        order = labeled(db, jan, 4)

        def pay():
            assert db.update_order(order.order_id, {"status": OrderStatus.COMPLETED.value})

        assert start_and_reply(handler, db, between=pay) == []
        assert db.get_order(order.order_id).status == OrderStatus.COMPLETED.value

    def test_the_ready_orders_move_and_are_listed(self, handler, db, jan):
        order = labeled(db, jan, 4)

        (message,) = start_and_reply(handler, db)

        assert message["user_id"] == 101
        assert db.get_order(order.order_id).status == OrderStatus.AWAITING_PAYMENT.value


class TestTheLinkOfTheCustomersBatch:
    """Each batch of 50 gets a link of its own (audit 5, B2): a reminder and /payment_info use the customer's"""

    FIRST, SECOND = "https://pay.example/first", "https://pay.example/second"

    @pytest.fixture
    def batches(self, handler, db):
        """51 customers with labeled orders, the two batches answered with their own link; (first, second) customer"""
        for n in range(51):
            customer = db.create_customer(
                Customer(
                    telegram_user_id=1000 + n,
                    first_name=f"Klant{n}",
                    authorization_status=AuthorizationStatus.APPROVED.value,
                )
            )
            labeled(db, customer, 1)
        handler.start_send_overviews(ADMIN_ID)
        stored = json.loads(db.get_edit_context_by_chat_id(ADMIN_ID).entity_id)["customers_data"]
        handler.handle_payment_link_input(ADMIN_ID, self.FIRST, db.get_edit_context_by_chat_id(ADMIN_ID).entity_id)
        handler.handle_payment_link_input(ADMIN_ID, self.SECOND, db.get_edit_context_by_chat_id(ADMIN_ID).entity_id)
        return db.get_customer(stored[0]["customer_id"]), db.get_customer(stored[50]["customer_id"])

    def test_a_reminder_carries_the_link_of_the_customers_batch(self, db, batches):
        reminders = OrderStatusManagement(db, ADMIN_ID, "prod", "token")
        reminders._send_message = Mock(return_value={"success": True})
        reminders._send_user_message = Mock(return_value={"success": True})
        reminders.handle_send_payment_reminder = Mock()

        for customer, link, other in ((batches[0], self.FIRST, self.SECOND), (batches[1], self.SECOND, self.FIRST)):
            reminders.handle_send_payment_reminder_to_customer(ADMIN_ID, customer.customer_id)
            message = reminders._send_user_message.call_args.args[1]
            assert link in message and other not in message

    def test_payment_info_shows_the_link_of_the_customers_batch(self, db, batches):
        info = CustomerOrderCommands(db, ADMIN_ID, "prod", "token")
        info._send_message = Mock(return_value={"success": True})

        first = batches[0]
        info.handle_payment_info(first.telegram_user_id, first.telegram_user_id)

        message = info._send_message.call_args.args[1]
        assert self.FIRST in message and self.SECOND not in message

    def test_an_order_moved_before_the_link_was_kept_uses_the_stored_link(self, db, jan):
        order = labeled(db, jan, 4)
        assert db.update_order(order.order_id, {"status": OrderStatus.AWAITING_PAYMENT.value})
        db.store_payment_link(self.SECOND)
        info = CustomerOrderCommands(db, ADMIN_ID, "prod", "token")
        info._send_message = Mock(return_value={"success": True})

        assert info.handle_payment_info(101, 101) == {"status": "success"}

        assert self.SECOND in info._send_message.call_args.args[1]
