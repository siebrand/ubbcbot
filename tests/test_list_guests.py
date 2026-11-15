"""/list_guests: lists the guest customers, with paging."""

from unittest.mock import Mock

import pytest

from handlers.admin.user_commands import UserCommands
from models.entities import AuthorizationStatus, Customer
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
CHAT_ID = 15005473
PAGE_SIZE = 20


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = UserCommands(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    return handler


def _guest(db, number, first_name="Gast", last_name=None, contact_info=None):
    created = db.create_customer(
        Customer(
            telegram_user_id=-1,
            first_name=first_name,
            last_name=last_name,
            username=f"GUEST_{number:03d}",
            authorization_status=AuthorizationStatus.APPROVED.value,
            is_guest=True,
            contact_info=contact_info,
        )
    )
    assert created
    return created


def _sent_text(handler) -> str:
    return handler._send_message.call_args.args[1]


def _sent_callbacks(handler) -> list[str]:
    markup = handler._send_message.call_args.kwargs.get("reply_markup") or {}
    return [b["callback_data"] for row in markup.get("inline_keyboard", []) for b in row]


def test_without_guests_it_says_so(handler):
    result = handler.handle_list_guests(CHAT_ID)

    assert result == {"status": "no_guests"}


def test_guests_are_listed_and_regular_customers_are_not(db, handler):
    _guest(db, 1, "Piet", "Puk", contact_info="piet@example.com")
    assert db.create_customer(
        Customer(
            telegram_user_id=4242,
            first_name="Jantje",
            username="jantje",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )

    result = handler.handle_list_guests(CHAT_ID)

    text = _sent_text(handler)
    assert result == {"status": "success"}
    assert "Piet Puk (GUEST_001) - piet@example.com" in text
    assert "Jantje" not in text


def test_guest_names_are_html_escaped(db, handler):
    _guest(db, 1, "<b>Piet</b>")

    handler.handle_list_guests(CHAT_ID)

    assert "<b>Piet</b>" not in _sent_text(handler)
    assert "&lt;b&gt;Piet&lt;/b&gt;" in _sent_text(handler)


def test_a_long_list_is_paged(db, handler):
    for number in range(1, PAGE_SIZE + 6):
        _guest(db, number)

    handler.handle_list_guests(CHAT_ID, 1)
    first = _sent_text(handler)
    first_buttons = _sent_callbacks(handler)
    handler.handle_list_guests(CHAT_ID, 2)
    second = _sent_text(handler)

    assert first.count("GUEST_") == PAGE_SIZE
    assert "GUEST_001" in first and "GUEST_021" not in first
    assert second.count("GUEST_") == 5
    assert "GUEST_021" in second
    assert "page_guests_2" in first_buttons
