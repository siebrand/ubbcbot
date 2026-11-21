"""A customer places an order, deletes old orders and asks what to pay, against the (mocked) database."""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.customer.order_commands import CustomerOrderCommands
from models.entities import AuthorizationStatus, Box, Customer, Offer, OfferStatus, Order
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
USER_ID = 4242
PRICE = Decimal("2.50")


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    service = DynamoDBService()
    service.create_offer(
        Offer(offer_id=7, name="Pils", price_per_unit=PRICE, wholesale_box_size=6, status=OfferStatus.ACTIVE.value)
    )
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def jan(db):
    return db.create_customer(
        Customer(
            telegram_user_id=USER_ID,
            first_name="Jan",
            location="Utrecht & Co",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


@pytest.fixture
def handler(db):
    handler = CustomerOrderCommands(db, ADMIN_ID, "prod", "token")
    handler.sent = []

    def send(chat, text, **kwargs):
        handler.sent.append((chat, text, kwargs))
        return {"success": True}

    handler._send_message = Mock(side_effect=send)
    handler.sync_offer_messages = Mock()
    handler._get_bot_username = Mock(return_value="ubbc_bot")
    return handler


def texts_to(handler, chat_id) -> list[str]:
    return [text for chat, text, _ in handler.sent if chat == chat_id]


def orders_of(db, customer) -> list[Order]:
    return db.get_orders_by_customer(customer.customer_id)


def order(db, customer, status, quantity=2, offer_id=7):
    created = Order(
        customer_id=customer.customer_id,
        box_id="b1",
        offer_id=offer_id,
        quantity=quantity,
        unit_price=PRICE,
        total_price=PRICE * quantity,
        status=status,
    )
    assert db.order_repo.create_order(created)
    return created


class TestPlaceAnOrder:
    def test_the_first_order_opens_a_box(self, db, handler, jan):
        result = handler.handle_create_order(USER_ID, USER_ID, ["7", "2"])

        assert result == {"status": "success"}
        [placed] = orders_of(db, jan)
        assert (placed.quantity, placed.status, placed.total_price) == (2, "pending", Decimal("5.00"))
        [box] = db.get_boxes_by_offer(7)
        assert (box.current_quantity, box.status) == (2, "open")
        assert any("Pils" in text for text in texts_to(handler, ADMIN_ID))

    def test_an_order_that_fills_the_box(self, db, handler, jan):
        assert db.create_box(Box(box_id="b1", offer_id=7, max_capacity=6, current_quantity=4))

        handler.handle_create_order(USER_ID, USER_ID, ["7", "2"])

        assert db.get_box("b1").status == "full"

    def test_a_delivered_box_with_room_goes_first(self, db, handler, jan):
        assert db.create_box(Box(box_id="dlvr", offer_id=7, max_capacity=6, current_quantity=4, status="delivered"))

        handler.handle_create_order(USER_ID, USER_ID, ["7", "2"])

        [placed] = orders_of(db, jan)
        assert (placed.box_id, placed.status) == ("dlvr", "ready_for_labeling")

    def test_more_than_a_box(self, db, handler, jan):
        db.update_offer(7, {"wholesale_box_size": 3})

        assert handler.handle_create_order(USER_ID, USER_ID, ["7", "4"]) == {"status": "quantity_too_large"}
        assert orders_of(db, jan) == []

    def test_more_than_the_limit_per_customer(self, db, handler, jan):
        assert handler.handle_create_order(USER_ID, USER_ID, ["7", "6"]) == {"status": "limit_exceeded"}
        assert orders_of(db, jan) == []

    @pytest.mark.parametrize("quantity", ["0", "-1"])
    def test_a_quantity_must_be_positive(self, handler, jan, quantity):
        assert handler.handle_create_order(USER_ID, USER_ID, ["7", quantity]) == {"status": "invalid_quantity"}

    def test_a_sold_out_offer(self, db, handler, jan):
        db.update_offer(7, {"status": OfferStatus.SOLD_OUT.value})

        assert handler.handle_create_order(USER_ID, USER_ID, ["7"]) == {"status": "validation_failed"}
        assert texts_to(handler, USER_ID) == [handler._t("offer_sold_out_named", USER_ID, offer_name="Pils")]

    def test_a_customer_who_is_not_approved(self, db, handler, jan):
        db.update_customer(jan.customer_id, {"authorization_status": AuthorizationStatus.UNAUTHORIZED.value})
        UserCache.invalidate_cache()

        assert handler.handle_create_order(USER_ID, USER_ID, ["7"]) == {"status": "validation_failed"}
        assert orders_of(db, jan) == []

    def test_a_second_order_asks_for_confirmation_and_names_the_status(self, db, handler, jan):
        handler.handle_create_order(USER_ID, USER_ID, ["7", "1"])
        handler.sent.clear()

        result = handler.handle_create_order(USER_ID, USER_ID, ["7", "2"])

        assert result == {"status": "confirmation_required"}
        warning = texts_to(handler, USER_ID)[0]
        assert f"({handler._t('status_pending', USER_ID)})" in warning
        assert "(pending)" not in warning
        assert len(orders_of(db, jan)) == 1

    def test_a_confirmed_second_order(self, db, handler, jan):
        handler.handle_create_order(USER_ID, USER_ID, ["7", "1"])

        assert handler.handle_confirm_order(USER_ID, USER_ID, ["7", "2"]) == {"status": "success"}
        assert sorted(o.quantity for o in orders_of(db, jan)) == [1, 2]


class TestDeleteOldOrders:
    @pytest.mark.parametrize(
        "command, status, other, done_key",
        [
            ("handle_delete_cancelled_orders", "cancelled", "completed", "cancelled_orders_deleted"),
            ("handle_delete_completed_orders", "completed", "cancelled", "completed_orders_deleted"),
        ],
    )
    def test_only_orders_with_that_status_go(self, db, handler, jan, command, status, other, done_key):
        order(db, jan, status)
        order(db, jan, status)
        kept = order(db, jan, other)

        result = getattr(handler, command)(USER_ID, USER_ID)

        assert result == {"status": "success", "deleted_count": 2}
        assert [o.order_id for o in orders_of(db, jan)] == [kept.order_id]
        assert texts_to(handler, USER_ID) == [handler._t(done_key, USER_ID, count=2)]

    @pytest.mark.parametrize(
        "command, result_status, key",
        [
            ("handle_delete_cancelled_orders", "no_cancelled_orders", "no_cancelled_orders"),
            ("handle_delete_completed_orders", "no_completed_orders", "no_completed_orders"),
        ],
    )
    def test_nothing_to_delete(self, handler, jan, command, result_status, key):
        assert getattr(handler, command)(USER_ID, USER_ID) == {"status": result_status}
        assert texts_to(handler, USER_ID) == [handler._t(key, USER_ID)]

    def test_an_unknown_customer(self, handler):
        assert handler.handle_delete_cancelled_orders(USER_ID, USER_ID) == {"status": "customer_not_found"}


class TestPaymentInfo:
    def test_what_to_pay_and_where(self, db, handler, jan):
        order(db, jan, "awaiting_payment", quantity=2)
        order(db, jan, "awaiting_payment", quantity=1)
        order(db, jan, "completed", quantity=5)
        assert db.store_payment_link("https://pay.example/abc")

        assert handler.handle_payment_info(USER_ID, USER_ID) == {"status": "success"}

        [text] = texts_to(handler, USER_ID)
        assert "3x [7] Pils" in text and "€7.50" in text
        assert "https://pay.example/abc" in text
        assert "Utrecht &amp; Co" in text  # sent as HTML
        assert handler.sent[-1][2]["parse_mode"] == "HTML"

    def test_nothing_to_pay(self, db, handler, jan):
        assert handler.handle_payment_info(USER_ID, USER_ID) == {"status": "no_orders"}

    def test_no_payment_link_yet(self, db, handler, jan):
        order(db, jan, "awaiting_payment")

        assert handler.handle_payment_info(USER_ID, USER_ID) == {"status": "no_payment_link"}


class TestWhichBoxAnOrderJoins:
    def test_an_ordered_box_with_room_makes_the_order_ordered(self, db, handler, jan):
        assert db.create_box(Box(box_id="ordr", offer_id=7, max_capacity=6, current_quantity=3, status="ordered"))

        handler.handle_create_order(USER_ID, USER_ID, ["7", "2"])

        [placed] = orders_of(db, jan)
        assert (placed.box_id, placed.status) == ("ordr", "ordered")
        assert (db.get_box("ordr").current_quantity, db.get_box("ordr").status) == (5, "ordered")

    def test_no_new_box_once_the_wholesale_order_is_placed(self, db, handler, jan):
        assert db.create_box(Box(box_id="ordr", offer_id=7, max_capacity=6, current_quantity=5, status="ordered"))

        assert handler.handle_create_order(USER_ID, USER_ID, ["7", "2"]) == {"status": "insufficient_space"}

        assert texts_to(handler, USER_ID) == [handler._t("order_too_large_for_remaining_space", USER_ID)]
        assert orders_of(db, jan) == []
        assert len(db.get_boxes_by_offer(7)) == 1

    def test_no_new_box_next_to_a_delivered_box(self, db, handler, jan):
        assert db.create_box(Box(box_id="dlvr", offer_id=7, max_capacity=6, current_quantity=6, status="delivered"))

        assert handler.handle_create_order(USER_ID, USER_ID, ["7", "1"]) == {"status": "insufficient_space"}

    def test_a_full_box_opens_a_second_one(self, db, handler, jan):
        assert db.create_box(Box(box_id="b1", offer_id=7, max_capacity=6, current_quantity=6, status="full"))

        handler.handle_create_order(USER_ID, USER_ID, ["7", "2"])

        [placed] = orders_of(db, jan)
        assert placed.box_id != "b1"
        assert db.get_box(placed.box_id).current_quantity == 2


class TestWhoIsTold:
    def test_the_group_and_the_admin_see_the_order_without_the_last_name(self, db, handler, jan, monkeypatch):
        monkeypatch.setenv("DEFAULT_GROUP_ID", "-100777")
        db.update_customer(jan.customer_id, {"last_name": "Jansen"})
        UserCache.invalidate_cache()

        handler.handle_create_order(USER_ID, USER_ID, ["7", "2"])

        [to_group] = texts_to(handler, -100777)
        assert "Jan J" in to_group and "Jansen" not in to_group
        assert texts_to(handler, ADMIN_ID) == [to_group]
        assert [kw.get("force_group") for chat, _, kw in handler.sent if chat == -100777] == [True]

    def test_an_order_placed_by_the_admin_is_not_announced(self, db, handler, jan, monkeypatch):
        monkeypatch.setenv("DEFAULT_GROUP_ID", "-100777")
        offer = db.get_offer(7)

        result = handler.execute_order(ADMIN_ID, ADMIN_ID, 2, offer, jan, placed_by_admin=True)

        assert result["status"] == "success"
        assert result["order"].quantity == 2  # the caller (/order_for) confirms it, in one message
        assert texts_to(handler, -100777) == []
        assert texts_to(handler, ADMIN_ID) == []


class TestOrderInput:
    @pytest.mark.parametrize(
        "args, status", [([], "invalid_args"), (["zeven"], "invalid_format"), (["7", "x"], "invalid_format")]
    )
    def test_bad_arguments(self, handler, jan, args, status):
        assert handler.handle_create_order(USER_ID, USER_ID, args)["status"] == status

    @pytest.mark.parametrize("status", ["draft", "inactive", "completed"])
    def test_an_offer_that_cannot_be_ordered(self, db, handler, jan, status):
        db.update_offer(7, {"status": status})

        assert handler.handle_create_order(USER_ID, USER_ID, ["7"]) == {"status": "validation_failed"}
        assert texts_to(handler, USER_ID) == [handler._t("offer_not_found", USER_ID)]

    def test_an_unknown_offer(self, handler, jan):
        assert handler.handle_create_order(USER_ID, USER_ID, ["99"]) == {"status": "validation_failed"}

    def test_someone_who_never_started_the_bot(self, handler):
        assert handler.handle_create_order(USER_ID, USER_ID, ["7"]) == {"status": "validation_failed"}
        assert texts_to(handler, USER_ID) == [handler._t("customer_not_found", USER_ID)]

    def test_a_failure_while_ordering_is_reported(self, db, handler, jan):
        handler._find_or_create_box = Mock(side_effect=RuntimeError("boom"))

        assert handler.handle_create_order(USER_ID, USER_ID, ["7"]) == {"status": "error"}
        assert texts_to(handler, USER_ID) == [handler._t("order_processing_failed", USER_ID)]
