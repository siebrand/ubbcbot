"""Customer lookup by (partial) customer ID, used by /update_user and the other name-based admin commands."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from handlers.admin.user_commands import UserCommands
from models.entities import AuthorizationStatus
from utils.validation import ValidationUtils

ADMIN_ID = 1
CHAT_ID = 1

ID_JAN = "3f2a9c1e-7b44-4d0a-9a51-0c2d5e8f1a11"
ID_JANE = "3f2a9c1e-aaaa-4d0a-9a51-0c2d5e8f1a22"
ID_ABE = "abe00000-1111-4d0a-9a51-0c2d5e8f1a33"


def _customer(customer_id, first_name, username=None):
    return SimpleNamespace(
        customer_id=customer_id,
        first_name=first_name,
        last_name=None,
        username=username,
        is_guest=False,
        contact_info=None,
        location=None,
        authorization_status=AuthorizationStatus.APPROVED.value,
    )


@pytest.fixture
def customers():
    return [_customer(ID_JAN, "Jan", "jan_b"), _customer(ID_JANE, "Jane"), _customer(ID_ABE, "Abe")]


@pytest.fixture
def validator(customers):
    db = Mock()
    db.get_customers_by_status.side_effect = lambda status: customers if status == "approved" else []
    return ValidationUtils(db, lambda key, *a, **kw: key)


class TestMatchByPartialId:
    def test_full_uuid_matches_one_customer(self, validator, customers):
        assert validator.match_customers(ID_JAN, customers) == [customers[0]]

    def test_first_eight_characters_match(self, validator, customers):
        assert validator.match_customers(ID_ABE[:8], customers) == [customers[2]]

    def test_prefix_is_case_insensitive(self, validator, customers):
        assert validator.match_customers(ID_JAN[:12].upper(), customers) == [customers[0]]

    def test_shared_prefix_returns_all_candidates(self, validator, customers):
        assert validator.match_customers("3f2a9c1e", customers) == [customers[0], customers[1]]

    def test_short_hex_like_name_still_matches_by_name(self, validator, customers):
        # "Abe" is all hex digits but shorter than 8 characters, so it must stay a name search.
        assert validator.match_customers("abe", customers) == [customers[2]]

    def test_unknown_id_falls_back_to_name_search_and_finds_nothing(self, validator, customers):
        assert validator.match_customers("deadbeef", customers) == []

    def test_id_match_wins_over_name_match(self, validator):
        decoy = _customer("11111111-0000-0000-0000-000000000000", "deadbeef-fan")
        target = _customer("deadbeef-0000-0000-0000-000000000000", "Someone")
        assert validator.match_customers("deadbeef", [decoy, target]) == [target]

    def test_name_search_unchanged(self, validator, customers):
        assert validator.match_customers("jan", customers) == [customers[0], customers[1]]


class TestUpdateUserCommand:
    @pytest.fixture
    def handler(self, validator, customers):
        handler = UserCommands(validator.db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        return handler

    def test_update_user_resolves_partial_customer_id(self, handler, customers):
        result = handler.handle_update_user(CHAT_ID, [ID_ABE[:8]])

        assert result == {"status": "success"}
        message, keyboard = handler._send_message.call_args.args[1], handler._send_message.call_args.kwargs
        assert "Abe" in message
        callbacks = [b["callback_data"] for row in keyboard["reply_markup"]["inline_keyboard"] for b in row]
        assert f"edit_customer_first_name_{ID_ABE}" in callbacks

    def test_update_user_resolves_full_customer_id(self, handler):
        result = handler.handle_update_user(CHAT_ID, [ID_JAN])

        assert result == {"status": "success"}
        assert "Jan" in handler._send_message.call_args.args[1]

    def test_update_user_with_ambiguous_prefix_shows_disambiguation(self, handler):
        result = handler.handle_update_user(CHAT_ID, ["3f2a9c1e"])

        assert result["status"] == "disambiguation_shown"
        keyboard = handler._send_message.call_args.kwargs["reply_markup"]
        callbacks = [b["callback_data"] for row in keyboard["inline_keyboard"] for b in row]
        assert f"edit_user_select_{ID_JAN}" in callbacks
        assert f"edit_user_select_{ID_JANE}" in callbacks

    def test_update_user_with_unknown_id_reports_not_found(self, handler):
        result = handler.handle_update_user(CHAT_ID, ["deadbeef"])

        assert result["status"] == "user_not_found"

    def test_update_user_by_name_still_works(self, handler):
        result = handler.handle_update_user(CHAT_ID, ["abe"])

        assert result == {"status": "success"}
