"""/list_credits: every customer whose balance is not zero, credit first, then the negative balances, against the
(mocked) database. The translations are the real ones (Dutch, the admin has no customer record)."""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.credit_commands import CreditCommands
from models.entities import AuthorizationStatus, Customer, CustomerCredit
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = CreditCommands(db, ADMIN_ID, "prod", "token")
    handler.sent = []
    handler._send_message = Mock(
        side_effect=lambda chat, text, **kw: handler.sent.append((chat, text, kw.get("reply_markup"))) or {}
    )
    return handler


def person(db, telegram_id, first, last=None, username=None, is_guest=False) -> Customer:
    return db.create_customer(
        Customer(
            telegram_user_id=telegram_id,
            first_name=first,
            last_name=last,
            username=username,
            is_guest=is_guest,
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def balance(db, customer_id: str, amount: str) -> None:
    assert db.create_customer_credit(CustomerCredit(customer_id=customer_id, current_balance=Decimal(amount)))


def text(handler) -> str:
    return handler.sent[-1][1]


def buttons(handler) -> list[str]:
    markup = handler.sent[-1][2] or {}
    return [b["callback_data"] for row in markup.get("inline_keyboard", []) for b in row]


def test_credit_and_negative_balances_in_their_order_without_zero(db, handler):
    jan, piet, kees = person(db, 1, "Jan", "Jansen", "jan"), person(db, 2, "Piet"), person(db, 3, "Kees")
    zero = person(db, 4, "Nul")
    balance(db, jan.customer_id, "5.00")
    balance(db, piet.customer_id, "12.50")
    balance(db, kees.customer_id, "-3.00")
    balance(db, zero.customer_id, "0")
    debtor = person(db, 5, "Schuld")
    balance(db, debtor.customer_id, "-7.25")

    assert handler.handle_list_credits(ADMIN_ID) == {"status": "success"}

    report = text(handler)
    assert report.index("Piet") < report.index("Jan Jansen (@jan)") < report.index("Schuld") < report.index("Kees")
    assert "€12.50" in report and "€5.00" in report and "-€7.25" in report and "-€3.00" in report
    assert "Nul" not in report
    assert "€17.50" in report  # the credit, together
    assert "-€10.25" in report  # the negative balances, together


def test_a_guest_and_a_deleted_customer(db, handler):
    guest = person(db, -1, None, username="GUEST_001", is_guest=True)
    balance(db, guest.customer_id, "2.00")
    balance(db, "abcdef12-gone-gone-gone-000000000000", "1.00")

    handler.handle_list_credits(ADMIN_ID)

    report = text(handler)
    assert "Onbekend" in report and "GUEST_001" in report
    assert "✗ abcdef12" in report


def test_more_than_one_page_with_the_totals_on_every_page(db, handler):
    for n in range(12):
        customer = person(db, 100 + n, f"Klant{n:02d}")
        balance(db, customer.customer_id, f"{n + 1}.00")
    debtor = person(db, 200, "Schuld")
    balance(db, debtor.customer_id, "-4.00")

    handler.handle_list_credits(ADMIN_ID)
    first = text(handler)
    assert "page_credits_2" in buttons(handler)
    handler.handle_list_credits(ADMIN_ID, 2)
    second = text(handler)

    assert "Klant11" in first and "Klant02" in first and "Klant01" not in first  # highest first, 10 a page
    assert "Klant01" in second and "Klant00" in second and "Schuld" in second
    for page in (first, second):
        assert "€78.00" in page and "-€4.00" in page  # 1 + 2 + ... + 12, and the debt


def test_nobody_with_a_balance(db, handler):
    zero = person(db, 4, "Nul")
    balance(db, zero.customer_id, "0")

    assert handler.handle_list_credits(ADMIN_ID) == {"status": "no_balances"}
    assert text(handler) == handler._t("list_credits_none", ADMIN_ID)


def test_a_failed_read_is_an_error_not_an_empty_list(db, handler):
    db.credit_repo._scan_items = Mock(side_effect=RuntimeError("boom"))

    assert handler.handle_list_credits(ADMIN_ID) == {"status": "error"}
    assert text(handler) == handler._t("list_credits_failed", ADMIN_ID)


def test_the_strict_read_raises_and_the_lenient_one_does_not(db):
    db.credit_repo._scan_items = Mock(side_effect=RuntimeError("boom"))

    assert db.get_customers_with_credit_balance() == []
    with pytest.raises(RuntimeError):
        db.get_customers_with_credit_balance(strict=True)
