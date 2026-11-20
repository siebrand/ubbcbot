"""The four admin screens that list approved customers with orders in a status (audit 5, B3): /send_delivery_overviews,
/process_payment, /failed_notifications, /send_payment_reminder, and the start of the overviews. Against the
mocked database, so the way the orders are read can change underneath."""

import json
from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.order.order_status import OrderStatusManagement
from models.entities import AuthorizationStatus, Box, Customer, Offer, Order, OrderStatus
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
BOX_ID = "abcdef12-0000-4000-8000-000000000000"
APPROVED = AuthorizationStatus.APPROVED.value


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


def person(db, telegram_user_id: int, first: str, last: str, status: str = APPROVED, guest: bool = False) -> Customer:
    return db.create_customer(
        Customer(
            telegram_user_id=telegram_user_id,
            first_name=first,
            last_name=last,
            username=first.lower(),
            authorization_status=status,
            is_guest=guest,
        )
    )


def order(db, customer: Customer, units: int, status: OrderStatus, received: int | None = None) -> Order:
    created = db.order_repo.create_order(
        Order(
            customer_id=customer.customer_id,
            box_id=BOX_ID,
            offer_id=7,
            quantity=units,
            received_quantity=units if received is None else received,
            unit_price=Decimal("1.00"),
            total_price=Decimal(units),
            status=status.value,
        )
    )
    assert created
    return created


@pytest.fixture
def people(db):
    """Approved customers with orders in several statuses, an unapproved one and a guest"""
    zoe = person(db, 101, "Zoe", "Aalders")
    bram = person(db, 102, "Bram", "Bakker")
    guest = person(db, -1, "Gast", "Gastmans", guest=True)
    blocked = person(db, 104, "Piet", "Puk", status=AuthorizationStatus.UNAUTHORIZED.value)
    idle = person(db, 105, "Ida", "Idle")
    ready = {
        "zoe": [
            order(db, zoe, 3, OrderStatus.LABELING_COMPLETED),
            order(db, zoe, 4, OrderStatus.LABELING_COMPLETED, received=1),
        ],
        "guest": [order(db, guest, 2, OrderStatus.LABELING_COMPLETED)],
    }
    order(db, blocked, 9, OrderStatus.LABELING_COMPLETED)
    order(db, blocked, 9, OrderStatus.AWAITING_PAYMENT)
    order(db, zoe, 5, OrderStatus.AWAITING_PAYMENT)
    order(db, bram, 6, OrderStatus.AWAITING_PAYMENT)
    order(db, bram, 2, OrderStatus.AWAITING_PAYMENT)
    order(db, bram, 8, OrderStatus.COMPLETED)
    order(db, idle, 1, OrderStatus.ORDERED)
    return {"zoe": zoe, "bram": bram, "guest": guest, "ready": ready}


def status_screen(db) -> OrderStatusManagement:
    handler = OrderStatusManagement(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"success": True})
    return handler


def texts(handler) -> str:
    return "\n".join(c.args[1] for c in handler._send_message.call_args_list)


def buttons(handler) -> list[str]:
    markup = handler._send_message.call_args.kwargs["reply_markup"]
    return [b["text"] for row in markup["inline_keyboard"] for b in row]


class TestTheScreens:
    def test_send_delivery_overviews_counts_the_approved_customers_with_labeled_orders(self, db, people):
        handler = status_screen(db)

        assert handler.handle_send_delivery_overviews(ADMIN_ID, []) == {"status": "confirmation_shown"}

        assert "Customers to notify: 2" in texts(handler)

    def test_process_payment_lists_the_approved_customers_awaiting_payment_by_last_name(self, db, people):
        handler = status_screen(db)

        assert handler.handle_process_payment(ADMIN_ID, []) == {"status": "customers_shown"}

        assert buttons(handler)[:2] == ["✓ Aalders, Zoe €5.00 (1)", "✓ Bakker, Bram €8.00 (2)"]
        assert not any("Puk" in b for b in buttons(handler))

    def test_failed_notifications_lists_the_approved_customers_with_labeled_orders(self, db, people):
        handler = status_screen(db)

        assert handler.handle_failed_notifications(ADMIN_ID, []) == {"status": "failed_shown"}

        text = texts(handler)
        assert "Zoe Aalders (@zoe):\n   💰 €7.00 (2 orders)" in text
        assert "Gast Gastmans (@gast):\n   💰 €2.00 (1 orders)" in text
        assert "Bram" not in text and "Piet" not in text

    def test_send_payment_reminder_lists_the_approved_customers_awaiting_payment(self, db, people):
        handler = status_screen(db)

        assert handler.handle_send_payment_reminder(ADMIN_ID, []) == {"status": "customers_shown"}

        assert buttons(handler)[:2] == ["🔔 Aalders, Zoe €5.00", "🔔 Bakker, Bram €8.00"]
        assert "Piet" not in texts(handler)

    def test_the_overviews_start_with_the_labeled_orders_split_and_guests_last(self, db, people):
        handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
        handler._send_message = Mock(return_value={"success": True})

        assert handler.start_send_overviews(ADMIN_ID) == {"status": "awaiting_payment_link"}

        stored = json.loads(db.get_edit_context_by_chat_id(ADMIN_ID).entity_id)["customers_data"]
        full, partial = people["ready"]["zoe"]
        assert stored == [
            {
                "customer_id": people["zoe"].customer_id,
                "delivered_order_ids": [full.order_id],
                "delayed_order_ids": [partial.order_id],
                "is_guest": False,
            },
            {
                "customer_id": people["guest"].customer_id,
                "delivered_order_ids": [people["ready"]["guest"][0].order_id],
                "delayed_order_ids": [],
                "is_guest": True,
            },
        ]

    def test_the_orders_are_read_by_status_not_per_customer(self, db, people):
        handler = status_screen(db)
        db.get_orders_by_customer = Mock(side_effect=AssertionError("a query per customer"))

        handler.handle_send_delivery_overviews(ADMIN_ID, [])
        handler.handle_process_payment(ADMIN_ID, [])
        handler.handle_failed_notifications(ADMIN_ID, [])
        handler.handle_send_payment_reminder(ADMIN_ID, [])
        overviews = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
        overviews._send_message = Mock(return_value={"success": True})
        assert overviews.start_send_overviews(ADMIN_ID) == {"status": "awaiting_payment_link"}

    def test_no_customers(self, db):
        handler = status_screen(db)

        assert handler.handle_send_delivery_overviews(ADMIN_ID, []) == {"status": "no_customers"}
        assert handler.handle_process_payment(ADMIN_ID, []) == {"status": "no_customers"}
        assert handler.handle_failed_notifications(ADMIN_ID, []) == {"status": "no_failed"}
        assert handler.handle_send_payment_reminder(ADMIN_ID, []) == {"status": "no_customers"}
