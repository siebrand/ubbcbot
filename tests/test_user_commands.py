"""Approving, rejecting and listing users (/approve_user, /reject_user, /user_status, /list_pending, /list_users)."""

from unittest.mock import Mock

import pytest

from handlers.admin.user_commands import UserCommands
from models.entities import AuthorizationStatus, Customer
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
CHAT_ID = 15005473
USER_ID = 4242


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = UserCommands(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._show_user_edit_interface = Mock(return_value={"status": "success"})
    return handler


def _customer(db, status=AuthorizationStatus.UNAUTHORIZED, **fields):
    values = {"telegram_user_id": USER_ID, "first_name": "Jan & Co", "last_name": "<Puk>", "username": "jan_puk"}
    values.update(fields)
    created = db.create_customer(Customer(authorization_status=status.value, **values))
    assert created
    return created


def _texts_to(handler, chat_id) -> list[str]:
    return [c.args[1] for c in handler._send_message.call_args_list if c.args[0] == chat_id]


def _stored_status(db, customer) -> str:
    UserCache.invalidate_cache()
    return db.get_customer(customer.customer_id).authorization_status


def _failing_for_user(chat_id, text, **kwargs):
    return {"success": chat_id != USER_ID}


class TestApprove:
    def test_the_user_is_approved_and_told(self, db, handler):
        customer = _customer(db)

        handler.handle_approve_user_by_id(CHAT_ID, customer.customer_id)

        assert _stored_status(db, customer) == AuthorizationStatus.APPROVED.value
        assert _texts_to(handler, USER_ID) == [handler._t("user_authorized", USER_ID)]
        assert handler._t("user_approved", CHAT_ID, name="Jan & Co") in _texts_to(handler, CHAT_ID)
        handler._show_user_edit_interface.assert_called_once()

    def test_the_admin_hears_when_the_user_did_not_get_the_message(self, db, handler):
        customer = _customer(db)
        handler._send_message.side_effect = _failing_for_user

        handler.handle_approve_user_by_id(CHAT_ID, customer.customer_id)

        admin_texts = _texts_to(handler, CHAT_ID)
        assert handler._t("user_not_notified", CHAT_ID, name="Jan & Co <Puk>") in admin_texts
        assert not any("jan_puk" in text or str(USER_ID) in text for text in admin_texts)

    def test_an_approved_user_is_not_approved_again(self, db, handler):
        customer = _customer(db, AuthorizationStatus.APPROVED)

        result = handler.handle_approve_user_by_id(CHAT_ID, customer.customer_id)

        assert result == {"status": "already_approved"}
        assert _texts_to(handler, USER_ID) == []

    def test_an_unknown_id(self, handler):
        assert handler.handle_approve_user_by_id(CHAT_ID, "nope") == {"status": "user_not_found"}


class TestReject:
    @pytest.mark.parametrize("entry", ["command", "button"])
    def test_the_user_is_rejected_and_told(self, db, handler, entry):
        customer = _customer(db)

        if entry == "command":
            result = handler.handle_reject_user(CHAT_ID, ["jan_puk"])
        else:
            result = handler.handle_reject_user_by_id(CHAT_ID, customer.customer_id)

        assert result == {"status": "success"}
        assert _stored_status(db, customer) == AuthorizationStatus.REJECTED.value
        assert _texts_to(handler, USER_ID) == [handler._t("access_rejected", USER_ID)]
        assert _texts_to(handler, CHAT_ID) == [handler._t("user_rejected", CHAT_ID, name="Jan & Co")]

    def test_the_admin_hears_when_the_user_did_not_get_the_message(self, db, handler):
        customer = _customer(db)
        handler._send_message.side_effect = _failing_for_user

        handler.handle_reject_user_by_id(CHAT_ID, customer.customer_id)

        assert handler._t("user_not_notified", CHAT_ID, name="Jan & Co <Puk>") in _texts_to(handler, CHAT_ID)

    def test_the_user_hears_it_in_their_own_language(self, db, handler):
        customer = _customer(db, language="en")

        handler.handle_reject_user_by_id(CHAT_ID, customer.customer_id)

        assert _texts_to(handler, USER_ID) == ["❌ Your access request has been rejected."]


class TestUserStatus:
    @pytest.mark.parametrize("entry", ["command", "button"])
    def test_status_with_the_name_as_typed(self, db, handler, entry):
        customer = _customer(db, AuthorizationStatus.APPROVED)

        if entry == "command":
            handler.handle_user_status(CHAT_ID, ["jan_puk"])
        else:
            handler.handle_user_status_select(CHAT_ID, customer.customer_id)

        assert _texts_to(handler, CHAT_ID) == [
            "✅ Jan & Co <Puk> (@jan_puk)\n" + handler._t("user_status_label", CHAT_ID, status="approved")
        ]


class TestLists:
    def test_pending_users_are_listed_as_typed(self, db, handler):
        _customer(db)
        _customer(db, telegram_user_id=4343, first_name="Kees", last_name=None, username=None)

        handler.handle_list_pending(CHAT_ID)

        text = _texts_to(handler, CHAT_ID)[0]
        assert "Jan & Co <Puk> (@jan_puk)" in text
        assert f"Kees {handler._t('no_username', CHAT_ID)}" in text
        assert handler._send_message.call_args.kwargs.get("parse_mode") is None

    def test_users_are_listed_as_typed(self, db, handler):
        _customer(db, AuthorizationStatus.APPROVED)

        handler.handle_list_users(CHAT_ID)

        assert "✅ Jan & Co <Puk> (@jan_puk)" in _texts_to(handler, CHAT_ID)[0]

    def test_a_search_without_results_is_translated(self, handler):
        handler.handle_list_users(CHAT_ID, search_string="zzz")

        search = " " + handler._t("matching_search", CHAT_ID, search="zzz")
        assert _texts_to(handler, CHAT_ID) == [handler._t("no_customers_found", CHAT_ID, status="all", search=search)]


class TestCreateGuest:
    def test_a_too_long_name_is_named_in_the_admins_language(self, handler):
        result = handler.handle_create_guest(CHAT_ID, ["x" * 101])

        assert result == {"status": "name_too_long"}
        field = handler._t("field_first_name", CHAT_ID)
        assert _texts_to(handler, CHAT_ID) == [handler._t("name_too_long", CHAT_ID, field=field)]


class TestApproveByName:
    def test_the_admin_types_the_username(self, db, handler):
        customer = _customer(db)

        handler.handle_approve_user(CHAT_ID, ["jan_puk"])

        assert _stored_status(db, customer) == AuthorizationStatus.APPROVED.value

    def test_an_approved_user_is_not_found_among_the_pending(self, db, handler):
        customer = _customer(db, AuthorizationStatus.APPROVED)

        assert handler.handle_approve_user(CHAT_ID, ["jan_puk"])["status"] == "user_not_found"
        assert _stored_status(db, customer) == AuthorizationStatus.APPROVED.value

    @pytest.mark.parametrize("method", ["handle_approve_user", "handle_reject_user", "handle_user_status"])
    def test_without_a_name_the_usage_is_shown(self, handler, method):
        assert getattr(handler, method)(CHAT_ID, []) == {"status": "invalid_args"}

    def test_the_choice_after_a_disambiguation_approves(self, db, handler):
        customer = _customer(db)

        handler.handle_approve_user_select(CHAT_ID, customer.customer_id)

        assert _stored_status(db, customer) == AuthorizationStatus.APPROVED.value

    @pytest.mark.parametrize(
        "method",
        [
            "handle_approve_user_select",
            "handle_reject_user_by_id",
            "handle_user_status_select",
            "handle_edit_user_select",
        ],
    )
    def test_a_button_for_a_user_that_is_gone(self, handler, method):
        assert getattr(handler, method)(CHAT_ID, "nope") == {"status": "user_not_found"}
        assert _texts_to(handler, CHAT_ID) == [handler._t("user_not_found", CHAT_ID, identifier="nope")]


class TestCreateGuestOrder:
    def test_a_guest_is_approved_numbered_and_never_messaged(self, db, handler):
        result = handler.handle_create_guest(CHAT_ID, ["Kees", "Bakker", "06", "1234"])

        assert result["status"] == "success"
        guest = next(c for c in db.get_all_customers() if c.username == result["guest_id"])
        assert (guest.first_name, guest.last_name, guest.contact_info) == ("Kees", "Bakker", "06 1234")
        assert guest.is_guest and guest.telegram_user_id < 0  # a negative id of its own, never a Telegram user
        assert guest.authorization_status == AuthorizationStatus.APPROVED.value

    def test_the_second_word_is_contact_info_when_it_is_an_address(self, db, handler):
        result = handler.handle_create_guest(CHAT_ID, ["Kees", "kees@example.com"])

        guest = next(c for c in db.get_all_customers() if c.username == result["guest_id"])
        assert (guest.last_name, guest.contact_info) == (None, "kees@example.com")

    def test_guest_numbers_count_up(self, handler):
        first = handler.handle_create_guest(CHAT_ID, ["Kees"])["guest_id"]
        second = handler.handle_create_guest(CHAT_ID, ["Klaas"])["guest_id"]

        assert first != second and first.startswith("GUEST_") and second.startswith("GUEST_")

    def test_without_a_name(self, handler):
        assert handler.handle_create_guest(CHAT_ID, []) == {"status": "invalid_args"}
