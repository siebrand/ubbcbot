"""Taking a customer's approval away: /reject_user and the button on the user edit screen, against the (moto)
database"""

from unittest.mock import Mock

import pytest

from handlers.admin.user_commands import UserCommands
from models.entities import AuthorizationStatus, Customer, Order
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def users(db):
    handler = UserCommands(db, ADMIN_ID, "prod", "token")
    handler.sent = []

    def send(chat, text, reply_markup=None, **_):
        buttons = [b["callback_data"] for row in (reply_markup or {}).get("inline_keyboard", []) for b in row]
        handler.sent.append((chat, text, buttons))
        return {"success": True}

    handler._send_message = Mock(side_effect=send)
    handler._notify_customer = Mock(return_value={"success": True})
    return handler


def approved(db, telegram_id, name):
    return db.create_customer(
        Customer(telegram_user_id=telegram_id, first_name=name, authorization_status=AuthorizationStatus.APPROVED.value)
    )


def status_of(db, customer) -> str:
    UserCache.invalidate_cache()
    return db.get_customer(customer.customer_id).authorization_status


def order(db, customer, status):
    assert db.order_repo.create_order(Order(customer_id=customer.customer_id, box_id="b1", offer_id=7, status=status))


class TestTheStatusOnTheEditScreen:
    """/update_user: the status can be changed, also back to approved after a rejection"""

    def test_the_edit_screen_has_a_status_button(self, db, users):
        jan = approved(db, 101, "Jan")

        users._show_user_edit_interface(jan, ADMIN_ID)

        assert f"edit_customer_status_{jan.customer_id}" in users.sent[-1][2]

    def test_a_rejected_guest_can_be_approved_again(self, db, users):
        guest = db.create_customer(
            Customer(telegram_user_id=-4, first_name="mutti", is_guest=True, authorization_status="rejected")
        )

        users._show_user_edit_interface(guest, ADMIN_ID)
        assert f"edit_customer_status_{guest.customer_id}" in users.sent[-1][2]

        users.handle_customer_status_options(ADMIN_ID, guest.customer_id)
        # a guest cannot sign up, so "pending" is not offered
        assert [b for b in users.sent[-1][2] if b.startswith("edit_customer_setstatus_")] == [
            f"edit_customer_setstatus_{guest.customer_id}_approved"
        ]

        assert users.handle_set_customer_status(ADMIN_ID, guest.customer_id, "approved")["status"] == "success"
        assert status_of(db, guest) == "approved"

    def test_a_guest_is_not_made_pending(self, db, users):
        guest = db.create_customer(
            Customer(telegram_user_id=-4, first_name="mutti", is_guest=True, authorization_status="approved")
        )

        assert users.handle_set_customer_status(ADMIN_ID, guest.customer_id, "unauthorized")["status"] == (
            "invalid_status"
        )
        assert status_of(db, guest) == "approved"

    def test_the_other_statuses_are_offered(self, db, users):
        jan = approved(db, 101, "Jan")

        users.handle_customer_status_options(ADMIN_ID, jan.customer_id)

        assert [b for b in users.sent[-1][2] if b.startswith("edit_customer_setstatus_")] == [
            f"edit_customer_setstatus_{jan.customer_id}_unauthorized",
            f"edit_customer_setstatus_{jan.customer_id}_rejected",
        ]

    def test_a_rejected_customer_can_be_approved_again(self, db, users):
        jan = approved(db, 101, "Jan")
        db.update_customer(jan.customer_id, {"authorization_status": "rejected"})

        result = users.handle_set_customer_status(ADMIN_ID, jan.customer_id, "approved")

        assert result["status"] == "success"
        assert status_of(db, jan) == "approved"
        assert users._notify_customer.call_args.args[1] == "user_authorized"

    def test_approval_is_withdrawn_from_a_customer_without_open_orders(self, db, users):
        jan = approved(db, 101, "Jan")
        order(db, jan, "completed")
        order(db, jan, "cancelled")

        users.handle_set_customer_status(ADMIN_ID, jan.customer_id, "rejected")

        assert status_of(db, jan) == "rejected"

    @pytest.mark.parametrize("new_status", ["rejected", "unauthorized"])
    @pytest.mark.parametrize("open_status", ["pending", "ready_for_labeling", "awaiting_payment"])
    def test_open_orders_are_warned_about_and_need_a_confirmation(self, db, users, new_status, open_status):
        jan = approved(db, 101, "Jan")
        order(db, jan, open_status)

        result = users.handle_set_customer_status(ADMIN_ID, jan.customer_id, new_status)

        assert result == {"status": "confirmation_required"}
        assert status_of(db, jan) == "approved"
        users._notify_customer.assert_not_called()
        _, warning, buttons = users.sent[-1]
        assert "1" in warning
        assert f"edit_customer_forcestatus_{jan.customer_id}_{new_status}" in buttons

    @pytest.mark.parametrize("new_status", ["rejected", "unauthorized"])
    def test_the_confirmation_changes_the_status_despite_the_open_orders(self, db, users, new_status):
        jan = approved(db, 101, "Jan")
        order(db, jan, "awaiting_payment")

        result = users.handle_set_customer_status(ADMIN_ID, jan.customer_id, new_status, confirmed=True)

        assert result == {"status": "success"}
        assert status_of(db, jan) == new_status

    def test_an_unknown_status_changes_nothing(self, db, users):
        jan = approved(db, 101, "Jan")

        assert users.handle_set_customer_status(ADMIN_ID, jan.customer_id, "vip")["status"] == "invalid_status"
        assert status_of(db, jan) == "approved"


class TestRejectUser:
    def test_a_customer_with_open_orders_is_warned_about_and_rejected_after_the_confirmation(self, db, users):
        jan = approved(db, 101, "Jan")
        order(db, jan, "ordered")

        assert users.handle_reject_user(ADMIN_ID, ["Jan"]) == {"status": "confirmation_required"}
        assert status_of(db, jan) == "approved"
        confirm = f"edit_customer_forcestatus_{jan.customer_id}_rejected"
        assert confirm in users.sent[-1][2] and "cancel_action" in users.sent[-1][2]

        users.handle_set_customer_status(ADMIN_ID, jan.customer_id, "rejected", confirmed=True)

        assert status_of(db, jan) == "rejected"
        assert users._notify_customer.call_args.args[1] == "access_rejected"

    def test_a_customer_without_open_orders_is_rejected_without_a_confirmation(self, db, users):
        jan = approved(db, 101, "Jan")
        order(db, jan, "completed")

        assert users.handle_reject_user(ADMIN_ID, ["Jan"]) == {"status": "success"}
        assert status_of(db, jan) == "rejected"

    def test_the_list_of_matches_rejects_the_customer_picked(self, db, users):
        approved(db, 101, "Jan")
        janneke = approved(db, 102, "Janneke")

        assert users.handle_reject_user(ADMIN_ID, ["Jan"])["status"] == "disambiguation_shown"

        buttons = users.sent[-1][2]
        assert f"reject_user_{janneke.customer_id}" in buttons  # not the edit screen
        users.handle_reject_user_by_id(ADMIN_ID, janneke.customer_id)
        assert status_of(db, janneke) == AuthorizationStatus.REJECTED.value
