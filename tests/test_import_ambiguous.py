"""CSV import: a name that matches more than one customer refuses the whole file, and lists the collisions."""

import re
from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.import_handler import ImportHandler
from models.entities import AuthorizationStatus, Customer, Offer, OfferStatus

ADMIN_ID = 15005473
CHAT_ID = 15005473

ALICE_A = Customer(
    customer_id="aaaaaaaa-1111-4111-8111-111111111111",
    telegram_user_id=1,
    first_name="Alice",
    last_name="Anders",
    username="alice_a",
    authorization_status=AuthorizationStatus.APPROVED.value,
)
ALICE_B = Customer(
    customer_id="bbbbbbbb-2222-4222-8222-222222222222",
    telegram_user_id=2,
    first_name="Alice",
    last_name="Bakker",
    username="alice_b",
    authorization_status=AuthorizationStatus.APPROVED.value,
)
BOB = Customer(
    customer_id="cccccccc-3333-4333-8333-333333333333",
    telegram_user_id=3,
    first_name="Bob",
    last_name="Claes",
    username="bobc",
    authorization_status=AuthorizationStatus.APPROVED.value,
)
CAREL = Customer(
    customer_id="dddddddd-4444-4444-8444-444444444444",
    telegram_user_id=4,
    first_name="Carel",
    last_name="Dekker",
    username="carel",
    authorization_status=AuthorizationStatus.REJECTED.value,
)
CAREL_TWIN = Customer(
    customer_id="eeeeeeee-5555-4555-8555-555555555555",
    telegram_user_id=5,
    first_name="Carel",
    last_name="Evers",
    username="carel_e",
    authorization_status=AuthorizationStatus.UNAUTHORIZED.value,
)


def _csv(*usernames: str) -> bytes:
    return ("offer_id,username\n" + "".join(f"7,{name}\n" for name in usernames)).encode()


@pytest.fixture
def handler():
    db = Mock()
    db.get_edit_context_by_chat_id.return_value = Mock(edit_type="import_csv", context_id="ctx")
    db.get_offer.return_value = Offer(
        offer_id=7, name="Pils", price_per_unit=Decimal("2.50"), status=OfferStatus.IMPORT.value
    )
    customers = {
        AuthorizationStatus.APPROVED.value: [ALICE_A, ALICE_B, BOB],
        AuthorizationStatus.UNAUTHORIZED.value: [CAREL_TWIN],
        AuthorizationStatus.REJECTED.value: [CAREL],
    }
    db.get_customers_by_status.side_effect = lambda status: customers.get(status, [])

    handler = ImportHandler(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._create_import_order = Mock(return_value={"success": True})
    return handler


def _upload(handler, csv_bytes: bytes):
    handler._download_file = Mock(return_value=csv_bytes)
    return handler.handle_document_upload(CHAT_ID, ADMIN_ID, "file-id", "orders.csv")


def _all_text(handler) -> str:
    return "\n".join(call.args[1] for call in handler._send_message.call_args_list)


def _buttons_sent(handler) -> list:
    return [c for c in handler._send_message.call_args_list if c.kwargs.get("reply_markup")]


class TestAmbiguousCustomer:
    def test_the_file_is_refused_and_nothing_is_imported(self, handler):
        # Line 2 is fine, line 3 is ambiguous: the good line must not be imported either
        result = _upload(handler, _csv("bobc", "alice"))

        assert result["status"] == "ambiguous_customers"
        handler._create_import_order.assert_not_called()

    def test_the_collisions_are_listed_with_name_username_and_id(self, handler):
        _upload(handler, _csv("bobc", "alice"))

        text = _all_text(handler)
        assert re.search(r"(Line|Regel) 3:", text)
        assert "alice" in text
        for customer in (ALICE_A, ALICE_B):
            assert f"{customer.first_name} {customer.last_name}" in text
            assert f"@{customer.username}" in text
            assert customer.customer_id[:8] in text
        assert "Bob" not in text

    def test_every_ambiguous_line_is_listed(self, handler):
        _upload(handler, _csv("alice", "bobc", "carel"))

        text = _all_text(handler)
        assert re.search(r"(Line|Regel) 2:", text)
        assert re.search(r"(Line|Regel) 4:", text)
        assert "Carel Dekker" in text and "Carel Evers" in text

    def test_there_are_no_buttons_to_tap(self, handler):
        _upload(handler, _csv("alice"))

        assert _buttons_sent(handler) == []

    def test_a_customer_id_prefix_resolves_the_collision(self, handler):
        result = _upload(handler, _csv(ALICE_A.customer_id[:8], ALICE_B.customer_id[:8]))

        assert result["status"] == "success"
        assert result["imported"] == 2
        assert [c.args[1] for c in handler._create_import_order.call_args_list] == [ALICE_A, ALICE_B]


class TestUnchangedBehaviour:
    def test_a_file_without_collisions_is_imported(self, handler):
        result = _upload(handler, _csv("bobc", "alice_a"))

        assert result["status"] == "success"
        assert result["imported"] == 2

    def test_an_unknown_name_is_a_line_error_and_the_other_lines_are_still_imported(self, handler):
        result = _upload(handler, _csv("bobc", "nobody"))

        assert result["imported"] == 1
        assert result["errors"] == 1
        assert re.search(r"(Line|Regel) 3:", _all_text(handler))
        assert _buttons_sent(handler) == []
