"""A payment amount and the oldest open orders it pays for (partial-payments-design.md, PP-1)"""

import itertools
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from models.entities import Order
from services.payment_matching import (
    MAX_MATCH_ORDERS,
    find_payment_match,
    parse_amount,
    selection_token,
)

START = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def open_order(n: int, total: str, credit: str = "0") -> Order:
    """The n-th oldest open order"""
    return Order(
        order_id=f"order-{n:03d}",
        total_price=Decimal(total),
        credit_applied=Decimal(credit),
        status="awaiting_payment",
        created_at=START,
        update_date=START + timedelta(hours=n),
    )


def ids(orders) -> list[str]:
    return [o.order_id for o in orders]


class TestParseAmount:
    @pytest.mark.parametrize(
        "text, amount",
        [
            ("40", "40.00"),
            ("40.5", "40.50"),
            ("40,50", "40.50"),
            ("€40.50", "40.50"),
            (" € 12 ", "12.00"),
            ("10000", "10000.00"),
        ],
    )
    def test_valid(self, text, amount):
        assert parse_amount(text) == Decimal(amount)

    @pytest.mark.parametrize("text", ["0", "0.00", "-5", "abc", "1.234", "10000.01", "", "1e3", "4,5,6"])
    def test_invalid(self, text):
        assert parse_amount(text) is None


class TestMatching:
    def test_one_order_exactly(self):
        orders = [open_order(1, "12.00"), open_order(2, "8.50")]

        result = find_payment_match(orders, Decimal("8.50"))

        assert ids(result.match.selected) == ["order-002"]

    def test_a_set_of_several(self):
        orders = [open_order(1, "12.00"), open_order(2, "8.50"), open_order(3, "20.00")]

        result = find_payment_match(orders, Decimal("20.50"))

        assert ids(result.match.selected) == ["order-001", "order-002"]

    def test_the_set_with_the_oldest_order_wins(self):
        orders = [open_order(3, "5.00"), open_order(1, "3.00"), open_order(2, "2.00")]  # stored in any order

        result = find_payment_match(orders, Decimal("5.00"))

        assert ids(result.match.selected) == ["order-001", "order-002"]  # not order-003 alone

    def test_no_match_gives_the_closest_total(self):
        orders = [open_order(1, "12.00"), open_order(2, "8.50"), open_order(3, "20.00")]

        result = find_payment_match(orders, Decimal("5.00"))

        assert result.match is None
        assert result.closest_total == Decimal("8.50")

    def test_the_lower_total_wins_a_tie(self):
        orders = [open_order(1, "4.00"), open_order(2, "6.00")]

        assert find_payment_match(orders, Decimal("5.00")).closest_total == Decimal("4.00")

    def test_zero_due_orders_are_settled_along_and_never_change_the_sum(self):
        orders = [open_order(1, "5.00", credit="5.00"), open_order(2, "7.25"), open_order(3, "3.00", credit="4.00")]

        result = find_payment_match(orders, Decimal("7.25"))

        assert ids(result.match.selected) == ["order-002"]
        assert ids(result.match.settle_with) == ["order-001", "order-003"]

    def test_amounts_that_are_not_whole_euros(self):
        orders = [open_order(1, "2.35"), open_order(2, "1.15"), open_order(3, "0.99")]

        assert ids(find_payment_match(orders, Decimal("3.34")).match.selected) == ["order-001", "order-003"]

    def test_a_debt_adds_to_the_amount_due(self):
        orders = [open_order(1, "5.00", credit="-2.00"), open_order(2, "4.00")]

        assert ids(find_payment_match(orders, Decimal("7.00")).match.selected) == ["order-001"]

    def test_an_empty_list(self):
        result = find_payment_match([], Decimal("5.00"))

        assert (result.match, result.closest_total, result.too_many) == (None, None, False)

    def test_more_than_the_maximum_number_of_orders_is_too_many(self):
        orders = [open_order(n, "1.00") for n in range(MAX_MATCH_ORDERS + 1)]

        assert find_payment_match(orders, Decimal("1.00")).too_many

    def test_a_total_above_the_cent_limit_is_too_many(self):
        orders = [open_order(n, "9999.00") for n in range(11)]

        assert find_payment_match(orders, Decimal("1.00")).too_many


def _brute_force(orders, target_cents):
    """The subset whose amounts add up to the target and that takes the oldest orders first, or None"""
    payable = sorted(orders, key=lambda o: o.update_date)
    amounts = [int(o.amount_due * 100) for o in payable]
    best = None
    for size in range(1, len(payable) + 1):
        for combo in itertools.combinations(range(len(payable)), size):
            if sum(amounts[i] for i in combo) == target_cents:
                key = tuple(1 if i in combo else 0 for i in range(len(payable)))
                if best is None or key > best[0]:
                    best = (key, [payable[i].order_id for i in combo])
    return best[1] if best else None


@pytest.mark.parametrize("seed", range(40))
def test_the_search_agrees_with_brute_force(seed):
    rng = random.Random(seed)
    orders = [open_order(n, f"{rng.randint(1, 1500) / 100:.2f}") for n in range(rng.randint(1, 10))]
    total = sum(int(o.amount_due * 100) for o in orders)

    for target in rng.sample(range(1, total + 2), min(25, total + 1)):
        result = find_payment_match(orders, Decimal(target) / 100)
        expected = _brute_force(orders, target)
        assert (ids(result.match.selected) if result.match else None) == expected


def test_the_token_does_not_depend_on_the_order_of_the_list():
    a, b, c = open_order(1, "1.00"), open_order(2, "2.00"), open_order(3, "3.00")

    assert selection_token([a, b, c]) == selection_token([c, a, b])
    assert selection_token([a, b]) != selection_token([a, c])
    assert len(selection_token([a])) == 6
