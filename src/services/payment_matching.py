"""A payment amount and the open orders it pays for (partial-payments-design.md).

Pure functions: no database and no Telegram. A payment settles a set of whole orders whose amounts due add up to
exactly the amount received. When several sets do, the one with the oldest order is chosen, then the next oldest, and
so on. The search is a bitset over cents: bit ``s`` of ``suffix[i]`` is set when the sum ``s`` can be made from the
orders from ``i`` on.
"""

import hashlib
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from models.entities import Order
from utils.timezone import to_utc_datetime

MAX_PAYMENT_AMOUNT = Decimal("10000")
MAX_MATCH_ORDERS = 60
MAX_MATCH_CENTS = 10_000_000

_AMOUNT = re.compile(r"^\d+(\.\d{1,2})?$")


@dataclass(frozen=True)
class PaymentMatch:
    selected: list[Order]  # oldest first, amounts due add up to the target
    settle_with: list[Order]  # zero-due orders, settled together with it


@dataclass(frozen=True)
class MatchResult:
    match: PaymentMatch | None
    closest_total: Decimal | None  # when there is no match
    too_many: bool = False


def parse_amount(text: str) -> Decimal | None:
    """The amount received: 40, 40.5, 40,50 or €40.50. More than 0, at most two decimals and at most
    MAX_PAYMENT_AMOUNT; None otherwise."""
    cleaned = (text or "").strip().removeprefix("€").strip().replace(",", ".")
    if not _AMOUNT.match(cleaned):
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if amount <= 0 or amount > MAX_PAYMENT_AMOUNT:
        return None
    return amount.quantize(Decimal("0.01"))


def age_key(order: Order) -> tuple:
    """Oldest first: the order open the longest (when it became awaiting_payment), then the oldest order, then its ID"""
    return (to_utc_datetime(order.update_date or order.created_at), to_utc_datetime(order.created_at), order.order_id)


def cents(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def find_payment_match(open_orders: list[Order], amount: Decimal) -> MatchResult:
    """The oldest set of open orders whose amounts due add up to ``amount``, with the zero-due orders to settle along;
    else the closest total that can be made (the lower one on a tie); ``too_many`` when the search is too large"""
    settle_with = sorted((o for o in open_orders if cents(o.amount_due) <= 0), key=age_key)
    payable = sorted((o for o in open_orders if cents(o.amount_due) > 0), key=age_key)
    amounts = [cents(o.amount_due) for o in payable]
    if len(payable) > MAX_MATCH_ORDERS or sum(amounts) > MAX_MATCH_CENTS:
        return MatchResult(match=None, closest_total=None, too_many=True)

    suffix = [0] * len(payable) + [1]
    for i in range(len(payable) - 1, -1, -1):
        suffix[i] = suffix[i + 1] | (suffix[i + 1] << amounts[i])

    target = cents(amount)
    if target > 0 and suffix[0] >> target & 1:
        selected, left = [], target
        for i, order in enumerate(payable):
            if left >= amounts[i] and suffix[i + 1] >> (left - amounts[i]) & 1:
                selected.append(order)
                left -= amounts[i]
        return MatchResult(match=PaymentMatch(selected=selected, settle_with=settle_with), closest_total=None)

    return MatchResult(match=None, closest_total=_closest(suffix[0] & ~1, target))


def _closest(sums: int, target: int) -> Decimal | None:
    """The reachable sum nearest to ``target`` (bit ``s`` of ``sums`` set: ``s`` can be made); the lower one wins a
    tie; None when nothing can be made"""
    if not sums:
        return None
    below = (sums & ((1 << (target + 1)) - 1)).bit_length() - 1  # -1 when none
    higher = sums >> (target + 1)
    above = target + 1 + (higher & -higher).bit_length() - 1 if higher else None
    candidates = [s for s in (below, above) if s is not None and s >= 0]
    best = min(candidates, key=lambda s: (abs(s - target), s))
    return Decimal(best) / 100


def selection_token(orders: list[Order]) -> str:
    """Six hex characters for a set of orders, whatever their order: the confirm button carries it, so a changed
    selection is noticed"""
    ids = ",".join(sorted(order.order_id for order in orders))
    return hashlib.sha1(ids.encode(), usedforsecurity=False).hexdigest()[:6]
