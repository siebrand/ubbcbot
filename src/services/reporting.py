"""Purchase reports from the order-history event store: periods, buckets and totals.

Only the calculations live here; the admin commands in handlers/admin/report_commands.py read the data and
format it. Periods and buckets follow the bot's local time (Europe/Amsterdam), so "a day" is a day as the
admin sees it. The events themselves are stored in UTC; the repository converts the bounds.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from models.entities import OrderStatus
from utils.timezone import CET, to_utc_datetime

YEAR_PATTERN = re.compile(r"^\d{4}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PERIOD_CODE_PATTERN = re.compile(r"^(\d{8})-(\d{8})$")

DAY, WEEK, MONTH, WEEKDAY = "day", "week", "month", "weekday"
GRANULARITY_WORDS = {
    "day": DAY,
    "dag": DAY,
    "week": WEEK,
    "month": MONTH,
    "maand": MONTH,
    "weekday": WEEKDAY,
}
PAID_WORDS = {"paid", "betaald"}
ANON_WORDS = {"anon", "anoniem"}

# Made-up names for /report_top_customers anon: a fresh random draw each time, never the same name twice in a report
ANON_NAMES = (
    "Petra Pils",
    "Sjaak Stout",
    "Karel Kriek",
    "Truus Tripel",
    "Gijs Gueuze",
    "Wim Witbier",
    "Bram Bock",
    "Doortje Dubbel",
    "Henk Hop",
    "Mieke Mout",
    "Gerrit Gist",
    "Liesbeth Lambiek",
    "Saskia Saison",
    "Bart Barleywine",
    "Ingrid IPA",
    "Pieter Porter",
    "Fenna Flesopener",
    "Klaas Kroonkurk",
    "Tamara Tapkraan",
    "Sem Schuimkraag",
    "Quinn Quadrupel",
    "Rianne Radler",
    "Willem Weizen",
    "Bea Brouwketel",
    "Kees Kelder",
    "Hanneke Hoppebel",
    "Fons Fust",
    "Greet Gerst",
    "Anton Amber",
    "Dirk Dubbelbock",
)

# Orders that are not paid yet: every status except paid (completed) and cancelled.
# Matches the outstanding total in base_order_handler.py.
CLOSED_ORDER_STATUSES = {OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value}

TOP_CUSTOMERS_LIMIT = 10

# Customers whose orders and payments are left out of the top-customer and sales reports (not /report_customer)
EXCLUDED_CUSTOMER_IDS = (
    "16f3c6d6-a32e-47d0-b3b6-22159aefde2b",
    "8a1bdd6b-c3c0-403d-9f49-b2f9acb738d4",
    "bc63908b-8f10-45a8-bb3e-cb89e5ea7e94",
)


class PeriodError(ValueError):
    """An argument that is not a valid period. ``value`` is the offending text, ``reason`` "invalid" or "future"."""

    def __init__(self, value: str, reason: str = "invalid"):
        super().__init__(value)
        self.value = value
        self.reason = reason


@dataclass(frozen=True)
class Period:
    """An inclusive range of local time: ``end`` is the last moment that is still part of the period"""

    start: datetime
    end: datetime

    @property
    def first_day(self) -> date:
        return self.start.date()

    @property
    def last_day(self) -> date:
        return self.end.date()

    @property
    def code(self) -> str:
        """Compact form for a button: YYYYMMDD-YYYYMMDD (whole days)"""
        return f"{self.first_day:%Y%m%d}-{self.last_day:%Y%m%d}"


@dataclass
class Bucket:
    count: int = 0
    amount: Decimal = Decimal("0")

    def add(self, amount: Decimal | None) -> None:
        self.count += 1
        self.amount += amount or Decimal("0")


@dataclass(frozen=True)
class CustomerTotal:
    customer_id: str
    amount: Decimal
    count: int


def _start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=CET)


def _end_of_day(day: date) -> datetime:
    """The last moment of a day, so a comparison with the end of a period includes the whole day"""
    return datetime.combine(day, time.max, tzinfo=CET)


def _parse_date(token: str) -> date:
    if not DATE_PATTERN.match(token):
        raise PeriodError(token)
    try:
        return date.fromisoformat(token)
    except ValueError:
        raise PeriodError(token) from None


def is_period_token(token: str) -> bool:
    """A word that looks like part of a period: a year (YYYY) or a date (YYYY-MM-DD)"""
    return bool(YEAR_PATTERN.match(token) or DATE_PATTERN.match(token))


def parse_period(tokens: list[str], now: datetime | None = None) -> Period:
    """The period of a report from its arguments.

    - nothing: the current year up to now
    - YYYY: that calendar year, 1 January through 31 December
    - YYYY-MM-DD: from that date through now
    - YYYY-MM-DD YYYY-MM-DD: from the earlier through the later date, in whatever order they are given

    A period never runs past now: there are no events in the future, and a report of this year should not
    list the months still to come.
    """
    now = (now or datetime.now(CET)).astimezone(CET)
    if not tokens:
        return Period(_start_of_day(date(now.year, 1, 1)), now)

    if len(tokens) == 1 and YEAR_PATTERN.match(tokens[0]):
        year = int(tokens[0])
        if year < 1:
            raise PeriodError(tokens[0])
        return Period(_start_of_day(date(year, 1, 1)), min(_end_of_day(date(year, 12, 31)), now))

    if len(tokens) == 1:
        start = _parse_date(tokens[0])
        if start > now.date():
            raise PeriodError(tokens[0], "future")
        return Period(_start_of_day(start), now)

    if len(tokens) == 2:
        first, second = sorted((_parse_date(tokens[0]), _parse_date(tokens[1])))
        if first > now.date():
            raise PeriodError(first.isoformat(), "future")
        return Period(_start_of_day(first), min(_end_of_day(second), now))

    raise PeriodError(" ".join(tokens))


def parse_period_code(code: str, now: datetime | None = None) -> Period:
    """The period of a button (see ``Period.code``). Like any period it ends at now at the latest."""
    match = PERIOD_CODE_PATTERN.match(code)
    if not match:
        raise PeriodError(code)
    try:
        first = datetime.strptime(match.group(1), "%Y%m%d").date()
        last = datetime.strptime(match.group(2), "%Y%m%d").date()
    except ValueError:
        raise PeriodError(code) from None
    if first > last:
        raise PeriodError(code)
    now = (now or datetime.now(CET)).astimezone(CET)
    return Period(_start_of_day(first), min(_end_of_day(last), now))


def split_trailing_period(args: list[str]) -> tuple[list[str], list[str]]:
    """Split ``<customer words> [period]``: at most two period words at the end are the period"""
    count = 0
    while count < 2 and count < len(args) and is_period_token(args[len(args) - 1 - count]):
        count += 1
    return args[: len(args) - count], args[len(args) - count :]


def local_moment(value) -> datetime:
    """An event time (datetime or ISO string, UTC) in local time"""
    return to_utc_datetime(value).astimezone(CET)


def bucket_start(day: date, granularity: str) -> date:
    """The first day of the bucket a day falls in. Weeks start on Monday (ISO-8601)."""
    if granularity == MONTH:
        return day.replace(day=1)
    if granularity == WEEK:
        return day - timedelta(days=day.weekday())
    return day


def _next_bucket(start: date, granularity: str) -> date:
    if granularity == MONTH:
        return date(start.year + start.month // 12, start.month % 12 + 1, 1)
    return start + timedelta(days=7 if granularity == WEEK else 1)


def bucket_starts(period: Period, granularity: str) -> list[date]:
    """Every bucket of the period, also those without events, oldest first"""
    starts = []
    current = bucket_start(period.first_day, granularity)
    while current <= period.last_day:
        starts.append(current)
        current = _next_bucket(current, granularity)
    return starts


def aggregate_by_bucket(events: Iterable, granularity: str) -> dict[date, Bucket]:
    """Count and amount of the events per bucket (keyed on the bucket's first day)"""
    buckets: dict[date, Bucket] = {}
    for event in events:
        key = bucket_start(local_moment(event.changed_at).date(), granularity)
        buckets.setdefault(key, Bucket()).add(event.amount)
    return buckets


def aggregate_by_weekday(events: Iterable) -> dict[int, Bucket]:
    """Count and amount of the events per day of the week in local time (0 = Monday, 6 = Sunday)"""
    weekdays: dict[int, Bucket] = {}
    for event in events:
        weekdays.setdefault(local_moment(event.changed_at).weekday(), Bucket()).add(event.amount)
    return weekdays


def weekday_occurrences(period: Period) -> list[int]:
    """How often each day of the week (0 = Monday) occurs from the period's first through its last day"""
    full_weeks, rest = divmod((period.last_day - period.first_day).days + 1, 7)
    occurrences = [full_weeks] * 7
    for offset in range(rest):
        occurrences[(period.first_day.weekday() + offset) % 7] += 1
    return occurrences


def without_excluded(events: Iterable) -> list:
    """The events of every customer except those in EXCLUDED_CUSTOMER_IDS"""
    return [event for event in events if event.customer_id not in EXCLUDED_CUSTOMER_IDS]


def total(events: Iterable) -> Bucket:
    result = Bucket()
    for event in events:
        result.add(event.amount)
    return result


def totals_per_customer(events: Iterable) -> list[CustomerTotal]:
    """Amount and number of events per customer, highest amount first"""
    per_customer: dict[str, Bucket] = {}
    for event in events:
        per_customer.setdefault(event.customer_id, Bucket()).add(event.amount)
    ranked = [CustomerTotal(customer_id, b.amount, b.count) for customer_id, b in per_customer.items()]
    return sorted(ranked, key=lambda t: (-t.amount, -t.count, t.customer_id))


def open_orders(orders: Iterable) -> list:
    """The orders that are not paid yet"""
    return [order for order in orders if order.status not in CLOSED_ORDER_STATUSES]


def bar(amount: Decimal, largest: Decimal, width: int = 10) -> str:
    """A bar of block characters, proportional to the largest amount. A small but non-zero amount shows a sliver."""
    if largest <= 0 or amount <= 0:
        return ""
    length = int((amount / largest * width).to_integral_value())
    return "█" * length if length else "▏"
