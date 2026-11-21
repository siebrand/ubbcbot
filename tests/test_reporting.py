"""Periods, buckets and totals of the purchase reports (services/reporting.py)"""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from services import reporting
from services.reporting import MONTH, WEEK, Period, PeriodError
from utils.timezone import CET

NOW = datetime(2026, 11, 18, 14, 30, tzinfo=CET)


def event(customer_id="c1", amount="10.00", at=datetime(2026, 3, 5, 12, 0, tzinfo=UTC)):
    return SimpleNamespace(customer_id=customer_id, amount=Decimal(amount) if amount else None, changed_at=at)


class TestParsePeriod:
    def test_no_argument_is_this_year_until_now(self):
        period = reporting.parse_period([], NOW)

        assert period.start == datetime(2026, 1, 1, tzinfo=CET)
        assert period.end == NOW

    def test_a_year_is_the_whole_calendar_year(self):
        period = reporting.parse_period(["2025"], NOW)

        assert period.start == datetime(2025, 1, 1, tzinfo=CET)
        assert period.end == datetime.combine(date(2025, 12, 31), time.max, tzinfo=CET)

    def test_the_current_year_stops_at_now(self):
        assert reporting.parse_period(["2026"], NOW).end == NOW

    def test_a_range_into_the_future_stops_at_now(self):
        assert reporting.parse_period(["2026-11-01", "2027-01-31"], NOW).end == NOW

    def test_a_range_that_starts_in_the_future_is_refused(self):
        with pytest.raises(PeriodError) as error:
            reporting.parse_period(["2027-01-31", "2027-01-01"], NOW)

        assert (error.value.reason, error.value.value) == ("future", "2027-01-01")

    def test_a_date_runs_until_now(self):
        period = reporting.parse_period(["2026-10-01"], NOW)

        assert period.start == datetime(2026, 10, 1, tzinfo=CET)
        assert period.end == NOW

    def test_today_is_allowed_as_start_date(self):
        assert reporting.parse_period(["2026-11-18"], NOW).first_day == date(2026, 11, 18)

    def test_a_start_date_in_the_future_is_refused(self):
        with pytest.raises(PeriodError) as error:
            reporting.parse_period(["2026-11-19"], NOW)

        assert error.value.reason == "future"
        assert error.value.value == "2026-11-19"

    def test_two_dates_include_the_whole_last_day_in_any_order(self):
        period = reporting.parse_period(["2026-02-28", "2026-02-01"], NOW)

        assert period.start == datetime(2026, 2, 1, tzinfo=CET)
        assert period.end == datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=CET)

    @pytest.mark.parametrize(
        "tokens",
        [["2026-13-01"], ["2026-02-30"], ["morgen"], ["20261118"], ["2026", "2026-01-01"], ["0000"], ["1", "2", "3"]],
    )
    def test_invalid_periods_are_refused(self, tokens):
        with pytest.raises(PeriodError) as error:
            reporting.parse_period(tokens, NOW)

        assert error.value.reason == "invalid"

    def test_the_default_now_is_in_local_time(self):
        period = reporting.parse_period([])

        assert period.end.tzinfo == CET


class TestPeriodCode:
    def test_a_period_survives_a_button(self):
        period = reporting.parse_period(["2025"], NOW)

        assert reporting.parse_period_code(period.code, NOW) == period

    def test_a_period_ending_today_runs_until_now(self):
        code = reporting.parse_period([], NOW).code

        assert code == "20260101-20261118"
        assert reporting.parse_period_code(code, NOW).end == NOW

    @pytest.mark.parametrize("code", ["2026", "20261301-20261302", "20261118-20261101", "abc12345", "x-y"])
    def test_a_broken_code_is_refused(self, code):
        with pytest.raises(PeriodError):
            reporting.parse_period_code(code, NOW)


class TestSplitTrailingPeriod:
    @pytest.mark.parametrize(
        "args, expected",
        [
            (["jan"], (["jan"], [])),
            (["jan", "jansen", "2025"], (["jan", "jansen"], ["2025"])),
            (["jan", "2026-01-01", "2026-02-01"], (["jan"], ["2026-01-01", "2026-02-01"])),
            (["2025", "2026-01-01", "2026-02-01"], (["2025"], ["2026-01-01", "2026-02-01"])),  # at most two
            (["2025"], ([], ["2025"])),
            ([], ([], [])),
        ],
    )
    def test_split(self, args, expected):
        assert reporting.split_trailing_period(args) == expected


class TestBuckets:
    def test_weeks_start_on_monday(self):
        assert reporting.bucket_start(date(2026, 11, 18), WEEK) == date(2026, 11, 16)

    def test_months_start_on_the_first(self):
        assert reporting.bucket_start(date(2026, 11, 18), MONTH) == date(2026, 11, 1)

    def test_every_month_of_a_period_is_a_bucket_also_across_new_year(self):
        period = reporting.parse_period(["2025-11-15", "2026-02-01"], NOW)

        assert reporting.bucket_starts(period, MONTH) == [
            date(2025, 11, 1),
            date(2025, 12, 1),
            date(2026, 1, 1),
            date(2026, 2, 1),
        ]

    def test_a_whole_year_has_twelve_months(self):
        assert len(reporting.bucket_starts(reporting.parse_period(["2025"], NOW), MONTH)) == 12

    def test_events_are_bucketed_in_local_time(self):
        """23:30 UTC on 31 December is already New Year in Amsterdam"""
        events = [event(at=datetime(2025, 12, 31, 23, 30, tzinfo=UTC)), event(at="2025-12-31T12:00:00+00:00")]

        buckets = reporting.aggregate_by_bucket(events, MONTH)

        assert {start: b.count for start, b in buckets.items()} == {date(2026, 1, 1): 1, date(2025, 12, 1): 1}

    def test_amounts_and_counts_are_summed_and_a_missing_amount_counts_as_zero(self):
        events = [event(amount="10.50"), event(amount="4.25"), event(amount=None)]

        bucket = reporting.aggregate_by_bucket(events, MONTH)[date(2026, 3, 1)]

        assert (bucket.count, bucket.amount) == (3, Decimal("14.75"))


class TestTotals:
    def test_customers_are_ranked_by_amount_then_count(self):
        events = [event("a", "5"), event("b", "20"), event("c", "5"), event("c", "0"), event("a", "1")]

        ranked = reporting.totals_per_customer(events)

        assert [(t.customer_id, t.amount, t.count) for t in ranked] == [
            ("b", Decimal("20"), 1),
            ("a", Decimal("6"), 2),
            ("c", Decimal("5"), 2),
        ]

    def test_total(self):
        result = reporting.total([event(amount="1.10"), event(amount="2.20")])

        assert (result.count, result.amount) == (2, Decimal("3.30"))

    def test_open_orders_are_all_but_completed_and_cancelled(self):
        statuses = [
            "pending",
            "ordered",
            "received_partial_delayed",
            "ready_for_labeling",
            "labeling_completed",
            "awaiting_payment",
            "completed",
            "cancelled",
        ]
        orders = [SimpleNamespace(status=status) for status in statuses]

        assert [o.status for o in reporting.open_orders(orders)] == statuses[:6]


class TestBar:
    def test_the_largest_amount_is_a_full_bar(self):
        assert reporting.bar(Decimal("50"), Decimal("50")) == "█" * 10

    def test_half(self):
        assert reporting.bar(Decimal("25"), Decimal("50")) == "█" * 5

    def test_a_tiny_amount_is_still_visible(self):
        assert reporting.bar(Decimal("0.01"), Decimal("50")) == "▏"

    def test_nothing_is_no_bar(self):
        assert reporting.bar(Decimal("0"), Decimal("50")) == ""
        assert reporting.bar(Decimal("0"), Decimal("0")) == ""


def test_period_days():
    period = Period(datetime(2026, 1, 1, tzinfo=CET), datetime(2026, 1, 31, 23, 59, tzinfo=CET))

    assert (period.first_day, period.last_day) == (date(2026, 1, 1), date(2026, 1, 31))
    assert period.code == "20260101-20260131"


class TestWeekdays:
    @staticmethod
    def period(first, last):
        return Period(datetime.combine(first, time.min, tzinfo=CET), datetime.combine(last, time.max, tzinfo=CET))

    def test_a_week_has_each_weekday_once(self):
        assert reporting.weekday_occurrences(self.period(date(2026, 11, 16), date(2026, 11, 22))) == [1] * 7

    def test_a_month(self):
        # November 2026 starts on a Sunday and ends on a Monday
        assert reporting.weekday_occurrences(self.period(date(2026, 11, 1), date(2026, 11, 30))) == [
            5,
            4,
            4,
            4,
            4,
            4,
            5,
        ]

    def test_a_year(self):
        # 2025 starts on a Wednesday: 53 Wednesdays
        assert reporting.weekday_occurrences(self.period(date(2025, 1, 1), date(2025, 12, 31))) == [
            52,
            52,
            53,
            52,
            52,
            52,
            52,
        ]

    def test_a_period_from_mid_week_to_mid_week(self):
        # Wednesday 18 through Thursday 26 November: two Wednesdays and Thursdays, one of the others
        assert reporting.weekday_occurrences(self.period(date(2026, 11, 18), date(2026, 11, 26))) == [
            1,
            1,
            2,
            2,
            1,
            1,
            1,
        ]

    def test_events_per_weekday_in_dutch_time(self):
        events = [
            event(amount="1", at=datetime(2026, 11, 16, 22, 59, tzinfo=UTC)),  # 23:59 Monday in Amsterdam
            event(amount="2", at=datetime(2026, 11, 16, 23, 1, tzinfo=UTC)),  # 00:01 Tuesday in Amsterdam
            event(amount="4", at=datetime(2026, 11, 22, 12, tzinfo=UTC)),  # Sunday
        ]

        per_day = reporting.aggregate_by_weekday(events)

        assert {day: (b.count, b.amount) for day, b in per_day.items()} == {
            0: (1, Decimal("1")),
            1: (1, Decimal("2")),
            6: (1, Decimal("4")),
        }

    def test_the_words(self):
        assert reporting.GRANULARITY_WORDS == {
            "day": reporting.DAY,
            "week": reporting.WEEK,
            "month": reporting.MONTH,
            "weekday": reporting.WEEKDAY,
        }
