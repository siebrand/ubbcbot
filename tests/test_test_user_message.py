"""/test_user_message <customer> <text>: sends a message from the admin's own account.

The customer is found like in the other admin commands (name, username, customer ID prefix, partial match). A plain
Telegram user ID still works. Anything that does not identify exactly one recipient is answered, never ignored:
a username used to raise inside the router, where the exception was swallowed and the admin got no answer.
"""

import json
from unittest.mock import Mock, patch

import pytest

from handlers.admin.test_commands import TestCommands as SetupDataCommands
from models.entities import AuthorizationStatus, Customer

ADMIN_ID = 15005473
CHAT_ID = ADMIN_ID

SIEBRAND = Customer(
    customer_id="aaaaaaaa-1111-4111-8111-111111111111",
    telegram_user_id=4242,
    first_name="Siebrand",
    last_name="Mazeland",
    username="siebrand",
    authorization_status=AuthorizationStatus.APPROVED.value,
)
ALICE_A = Customer(
    customer_id="bbbbbbbb-2222-4222-8222-222222222222",
    telegram_user_id=5001,
    first_name="Alice",
    last_name="Anders",
    username="alice_a",
    authorization_status=AuthorizationStatus.APPROVED.value,
)
ALICE_B = Customer(
    customer_id="cccccccc-3333-4333-8333-333333333333",
    telegram_user_id=5002,
    first_name="Alice",
    last_name="Bakker",
    username="alice_b",
    authorization_status=AuthorizationStatus.APPROVED.value,
)
CAREL_PENDING = Customer(
    customer_id="dddddddd-4444-4444-8444-444444444444",
    telegram_user_id=6001,
    first_name="Carel",
    last_name="Dekker",
    username="carel",
    authorization_status=AuthorizationStatus.UNAUTHORIZED.value,
)
DIRK_REJECTED = Customer(
    customer_id="eeeeeeee-5555-4555-8555-555555555555",
    telegram_user_id=6002,
    first_name="Dirk",
    last_name="Evers",
    username="dirk",
    authorization_status=AuthorizationStatus.REJECTED.value,
)


@pytest.fixture
def handler():
    customers = {
        AuthorizationStatus.APPROVED.value: [SIEBRAND, ALICE_A, ALICE_B],
        AuthorizationStatus.UNAUTHORIZED.value: [CAREL_PENDING],
        AuthorizationStatus.REJECTED.value: [DIRK_REJECTED],
    }
    db = Mock()
    db.get_customers_by_status.side_effect = lambda status: customers.get(status, [])
    db.get_customer_by_telegram_id.return_value = None  # the admin has no language of their own: Dutch
    with patch("handlers.admin.test_commands.boto3.client"):
        handler = SetupDataCommands(db, ADMIN_ID, "prod", "token")
    handler.message_sender_lambda = "ubbc-bot-prod-message-sender"
    handler.lambda_client = Mock()
    handler.lambda_client.invoke.return_value = {"Payload": _payload({"success_count": 1})}
    handler._send_message = Mock(return_value={"success": True})
    return handler


def _payload(body: dict):
    return Mock(read=Mock(return_value=json.dumps({"body": json.dumps(body)}).encode()))


def _sent(handler) -> str:
    return handler._send_message.call_args.args[1]


def _sent_to(handler) -> int:
    return json.loads(handler.lambda_client.invoke.call_args.kwargs["Payload"])["messages"][0]["user_id"]


class TestArguments:
    @pytest.mark.parametrize("args", [[], ["siebrand"]], ids=["nothing", "recipient only"])
    def test_missing_arguments_show_the_usage(self, handler, args):
        result = handler.handle_test_user_message(CHAT_ID, args)

        assert result == {"status": "invalid_args"}
        handler.lambda_client.invoke.assert_not_called()
        assert "/test_user_message" in _sent(handler)


class TestFindingTheRecipient:
    @pytest.mark.parametrize(
        "identifier", ["siebrand", "Siebrand", "sieb", "mazeland", "siebrand mazeland", SIEBRAND.customer_id[:8]]
    )
    def test_the_customer_is_found_like_in_other_commands(self, handler, identifier):
        result = handler.handle_test_user_message(CHAT_ID, [identifier, "test"])

        assert result == {"status": "success"}
        assert _sent_to(handler) == SIEBRAND.telegram_user_id

    @pytest.mark.parametrize("identifier", ["carel", "Dekker", CAREL_PENDING.customer_id[:8], "dirk", "Evers"])
    def test_only_approved_customers_are_taken_into_account(self, handler, identifier):
        result = handler.handle_test_user_message(CHAT_ID, [identifier, "test"])

        assert result == {"status": "user_not_found"}
        handler.lambda_client.invoke.assert_not_called()

    def test_a_name_shared_with_a_customer_who_is_not_approved_is_not_ambiguous(self, handler):
        handler._send_message.reset_mock()
        handler.db.get_customers_by_status.side_effect = lambda status: {
            AuthorizationStatus.APPROVED.value: [SIEBRAND],
            AuthorizationStatus.UNAUTHORIZED.value: [
                Customer(telegram_user_id=1, first_name="Siebrand", username="siebrand2")
            ],
        }.get(status, [])

        result = handler.handle_test_user_message(CHAT_ID, ["siebrand", "test"])

        assert result == {"status": "success"}
        assert _sent_to(handler) == SIEBRAND.telegram_user_id

    def test_a_telegram_user_id_that_is_not_a_customer_is_used_as_it_is(self, handler):
        result = handler.handle_test_user_message(CHAT_ID, ["777000", "test"])

        assert result == {"status": "success"}
        assert _sent_to(handler) == 777000

    def test_an_unknown_name_is_reported(self, handler):
        result = handler.handle_test_user_message(CHAT_ID, ["nobody", "test"])

        assert result == {"status": "user_not_found"}
        handler.lambda_client.invoke.assert_not_called()
        assert "nobody" in _sent(handler)

    def test_a_name_that_fits_several_customers_is_refused_with_the_candidates(self, handler):
        result = handler.handle_test_user_message(CHAT_ID, ["alice", "test"])

        assert result == {"status": "ambiguous_customer"}
        handler.lambda_client.invoke.assert_not_called()
        text = _sent(handler)
        for customer in (ALICE_A, ALICE_B):
            assert f"{customer.first_name} {customer.last_name}" in text
            assert f"@{customer.username}" in text
            assert customer.customer_id[:8] in text
        assert "Siebrand" not in text
        assert "reply_markup" not in handler._send_message.call_args.kwargs

    def test_a_customer_id_prefix_resolves_the_collision(self, handler):
        handler.handle_test_user_message(CHAT_ID, [ALICE_B.customer_id[:8], "test"])

        assert _sent_to(handler) == ALICE_B.telegram_user_id


class TestSending:
    def test_the_message_is_sent_from_the_admin_account(self, handler):
        result = handler.handle_test_user_message(CHAT_ID, ["siebrand", "hello", "there"])

        assert result == {"status": "success"}
        call = handler.lambda_client.invoke.call_args.kwargs
        assert call["FunctionName"] == "ubbc-bot-prod-message-sender"
        assert json.loads(call["Payload"]) == {
            "messages": [{"user_id": 4242, "message": "hello there", "from_admin": True}],
            "environment": "prod",
            "admin_language": "nl",
        }
        assert "4242" in _sent(handler)

    def test_a_failure_of_the_sender_is_reported(self, handler):
        handler.lambda_client.invoke.return_value = {
            "Payload": _payload({"success_count": 0, "results": [{"error": "user not found"}]})
        }

        result = handler.handle_test_user_message(CHAT_ID, ["siebrand", "hello"])

        assert result == {"status": "error"}
        assert "user not found" in _sent(handler)

    def test_an_exception_is_reported(self, handler):
        handler.lambda_client.invoke.side_effect = RuntimeError("no such function")

        result = handler.handle_test_user_message(CHAT_ID, ["siebrand", "hello"])

        assert result == {"status": "error"}
        assert "no such function" in _sent(handler)
