"""/subscribe: the message a Dutch customer gets.

The text must read as Dutch, say what happens, and name the command to undo it (which must exist for customers).
"""

from unittest.mock import Mock

import pytest

from handlers.customer.info_commands import InfoCommands
from models.entities import AuthorizationStatus, Customer
from services.routing.command_table import COMMAND_ROUTES

ADMIN_ID = 15005473
USER_ID = 4242
CHAT_ID = 4242


@pytest.fixture
def customer():
    return Customer(
        telegram_user_id=USER_ID,
        first_name="Jantje",
        language="nl",
        authorization_status=AuthorizationStatus.APPROVED.value,
    )


@pytest.fixture
def handler(customer):
    db = Mock()
    db.get_customer_by_telegram_id.return_value = customer
    db.update_customer.return_value = True
    handler = InfoCommands(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"success": True})
    return handler


def _sent(handler) -> str:
    return handler._send_message.call_args.args[1]


class TestSubscribeMessage:
    def test_the_customer_is_subscribed(self, handler, customer):
        result = handler.handle_subscribe(CHAT_ID, USER_ID)

        assert result == {"status": "success"}
        handler.db.update_customer.assert_called_once_with(customer.customer_id, {"subscribed_to_offers": True})

    def test_the_message_says_you_are_subscribed(self, handler):
        handler.handle_subscribe(CHAT_ID, USER_ID)

        text = _sent(handler)
        assert text.startswith("✅")
        assert "geabonneerd" in text.lower()

    def test_the_message_says_what_you_will_get(self, handler):
        handler.handle_subscribe(CHAT_ID, USER_ID)

        text = _sent(handler).lower()
        assert "nieuwe aanbieding" in text
        assert "privébericht" in text

    def test_the_message_does_not_split_the_compound_noun(self, handler):
        """'aanbieding meldingen' is not Dutch: it is one word or a different phrasing"""
        handler.handle_subscribe(CHAT_ID, USER_ID)

        assert "aanbieding meldingen" not in _sent(handler).lower()

    def test_the_message_tells_how_to_unsubscribe_with_a_command_that_exists_for_customers(self, handler):
        handler.handle_subscribe(CHAT_ID, USER_ID)

        assert "/unsubscribe" in _sent(handler)
        assert "/unsubscribe" in COMMAND_ROUTES
        assert not COMMAND_ROUTES["/unsubscribe"].admin_only

    def test_the_message_is_a_short_message_without_markup(self, handler):
        handler.handle_subscribe(CHAT_ID, USER_ID)

        assert len(_sent(handler)) < 200
        assert "<" not in _sent(handler)
        assert "parse_mode" not in handler._send_message.call_args.kwargs

    def test_a_failed_subscription_is_reported_and_not_confirmed(self, handler):
        handler.db.update_customer.return_value = False

        result = handler.handle_subscribe(CHAT_ID, USER_ID)

        assert result == {"status": "error"}
        assert "geabonneerd" not in _sent(handler).lower()
