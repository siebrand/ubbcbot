"""The admin report commands: what the admin sees for /report_top_customers, /report_sales_by_period and
/report_customer. The database is a mock; the translations are the real ones (Dutch, the admin's default)."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from handlers.admin.report_commands import MESSAGE_LIMIT, NAME_WIDTH, ReportCommands
from models.entities import Customer, Order
from services.reporting import ANON_NAMES, EXCLUDED_CUSTOMER_IDS, TOP_CUSTOMERS_LIMIT

ADMIN_ID = 15005473
THIS_YEAR = datetime.now(UTC).year
EXCLUDED = EXCLUDED_CUSTOMER_IDS[0]


def payment(customer_id, amount, at=None, event_type="PAYMENT_RECEIVED"):
    at = at or datetime(THIS_YEAR, 1, 10, 12, tzinfo=UTC)
    return SimpleNamespace(customer_id=customer_id, amount=Decimal(amount), changed_at=at, event_type=event_type)


def customer(customer_id, first_name, last_name=None, username=None):
    return Customer(customer_id=customer_id, first_name=first_name, last_name=last_name, username=username)


@pytest.fixture
def env():
    db = Mock()
    db.get_customer_by_telegram_id.return_value = None  # the admin has no customer record: Dutch
    db.get_events_by_type.return_value = []
    db.get_order_history_by_customer.return_value = []
    db.get_orders_by_customer.return_value = []
    db.get_customers_by_status.return_value = []
    db.get_customer.return_value = None
    handler = ReportCommands(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"success": True})
    return SimpleNamespace(handler=handler, db=db)


def sent(env) -> list[str]:
    return [c.args[1] for c in env.handler._send_message.call_args_list]


def text(env) -> str:
    return "\n".join(sent(env))


def known_customers(env, *customers):
    by_id = {c.customer_id: c for c in customers}
    env.db.get_customer.side_effect = by_id.get
    env.db.get_customers_by_status.side_effect = lambda status: list(customers) if status == "approved" else []


class TestTopCustomers:
    def test_customers_are_ranked_by_amount_paid_with_public_names(self, env):
        known_customers(env, customer("c1", "Jan", "Jansen"), customer("c2", "Piet", "Puk"))
        env.db.get_events_by_type.return_value = [payment("c1", "10"), payment("c2", "25.50"), payment("c1", "5")]

        result = env.handler.handle_report_top_customers(ADMIN_ID, [])

        assert result == {"status": "success"}
        report = text(env)
        assert report.index("Piet P") < report.index("Jan J")
        assert "Jansen" not in report and "Puk" not in report  # never the full last name
        assert "25.50" in report and "15.00" in report
        assert "€40.50" in report  # the total
        env.handler._send_message.assert_called_with(ADMIN_ID, sent(env)[-1], parse_mode="HTML")

    def test_payments_of_the_period_are_read_strictly(self, env):
        env.handler.handle_report_top_customers(ADMIN_ID, ["2025"])

        event_type, start, end = env.db.get_events_by_type.call_args.args
        assert event_type == "PAYMENT_RECEIVED"
        assert (start.year, start.month, start.day) == (2025, 1, 1)
        assert (end.year, end.month, end.day, end.hour, end.minute) == (2025, 12, 31, 23, 59)
        assert env.db.get_events_by_type.call_args.kwargs == {"strict": True}

    def test_a_deleted_customer_is_shown_as_deleted_with_the_short_id(self, env):
        env.db.get_events_by_type.return_value = [payment("abcdef12-3456", "10")]

        env.handler.handle_report_top_customers(ADMIN_ID, [])

        assert " 1. ✗ abcdef12" in text(env)
        assert "✗ = verwijderde klant" in text(env)

    def test_the_deleted_legend_only_appears_when_needed(self, env):
        known_customers(env, customer("c1", "Jan", "Jansen"))
        env.db.get_events_by_type.return_value = [payment("c1", "10")]

        env.handler.handle_report_top_customers(ADMIN_ID, [])

        assert "verwijderde klant" not in text(env)

    def test_names_are_escaped(self, env):
        known_customers(env, customer("c1", "<b>Evil</b>", "&Co"))
        env.db.get_events_by_type.return_value = [payment("c1", "10")]

        env.handler.handle_report_top_customers(ADMIN_ID, [])

        assert "<b>Evil" not in text(env)
        assert "&lt;b&gt;Evil" in text(env)

    def test_a_customer_without_name_falls_back_to_the_username(self, env):
        known_customers(env, customer("c1", None, None, username="beerlover"))
        env.db.get_events_by_type.return_value = [payment("c1", "10")]

        env.handler.handle_report_top_customers(ADMIN_ID, [])

        assert "beerlover" in text(env)

    def test_only_the_top_ten_are_listed(self, env):
        env.db.get_events_by_type.return_value = [payment(f"cust{i:02d}xx", str(i + 1)) for i in range(12)]

        env.handler.handle_report_top_customers(ADMIN_ID, [])

        report = text(env)
        assert "10. " in report and "11. " not in report
        assert "Klanten: 12" in report
        assert "staat in de lijst" not in report
        assert "Top 10: €75.00, 96.2% van het totaal" in report  # 3 + 4 + … + 12 of 1 + 2 + … + 12 = 78

    def test_the_share_of_the_top_is_all_when_every_customer_is_listed(self, env):
        env.db.get_events_by_type.return_value = [payment("c1", "10"), payment("c2", "30")]

        env.handler.handle_report_top_customers(ADMIN_ID, [])

        assert "Top 2: €40.00, 100.0% van het totaal" in text(env)

    def test_no_share_when_nothing_was_paid(self, env):
        env.db.get_events_by_type.return_value = [payment("c1", "0")]

        assert env.handler.handle_report_top_customers(ADMIN_ID, []) == {"status": "success"}
        assert "van het totaal" not in text(env)

    def test_no_payments(self, env):
        assert env.handler.handle_report_top_customers(ADMIN_ID, []) == {"status": "no_data"}
        assert "Geen betalingen" in text(env)

    def test_an_excluded_customer_is_not_ranked_or_counted(self, env):
        known_customers(env, customer("c1", "Jan", "Jansen"), customer(EXCLUDED, "Piet", "Puk"))
        env.db.get_events_by_type.return_value = [payment("c1", "10"), payment(EXCLUDED, "500")]

        assert env.handler.handle_report_top_customers(ADMIN_ID, []) == {"status": "success"}

        report = text(env)
        assert "Piet P" not in report and "500.00" not in report
        assert "€10.00" in report  # the total
        assert "Klanten: 1" in report

    @pytest.mark.parametrize("word", ["anon", "Anoniem"])
    def test_anon_shows_made_up_names_only(self, env, word):
        known_customers(env, customer("c1", "Jan", "Jansen"), customer("c2", "Piet", "Puk"))
        env.db.get_events_by_type.return_value = [
            payment("c1", "10"),
            payment("c2", "25.50"),
            payment("abcdef12-3456", "5"),  # a deleted customer
        ]

        assert env.handler.handle_report_top_customers(ADMIN_ID, ["2025", word]) == {"status": "success"}

        report = text(env)
        assert "Jan" not in report and "Piet P" not in report
        assert "abcdef12" not in report and "verwijderde klant" not in report
        shown = [name for name in ANON_NAMES if name in report]
        assert len(shown) == 3
        assert "25.50" in report and "€40.50" in report and "Klanten: 3" in report
        assert env.db.get_events_by_type.call_args.args[1].year == 2025  # the word is not read as a period

    def test_anon_names_differ_between_runs(self, env):
        env.db.get_events_by_type.return_value = [payment(f"cust{i:02d}xx", str(i + 1)) for i in range(10)]

        reports = set()
        for _ in range(5):
            env.handler._send_message.reset_mock()
            env.handler.handle_report_top_customers(ADMIN_ID, ["anon"])
            reports.add(text(env))

        assert len(reports) > 1

    def test_anon_names_are_unique_and_fit_the_name_column(self):
        assert len(set(ANON_NAMES)) == len(ANON_NAMES) >= TOP_CUSTOMERS_LIMIT
        assert all(len(name) <= NAME_WIDTH for name in ANON_NAMES)

    @pytest.mark.parametrize("excluded", EXCLUDED_CUSTOMER_IDS)
    def test_only_payments_of_an_excluded_customer_is_no_data(self, env, excluded):
        env.db.get_events_by_type.return_value = [payment(excluded, "500")]

        assert env.handler.handle_report_top_customers(ADMIN_ID, []) == {"status": "no_data"}
        assert "Geen betalingen" in text(env)

    def test_a_failed_read_is_an_error_not_an_empty_report(self, env):
        env.db.get_events_by_type.side_effect = RuntimeError("boom")

        assert env.handler.handle_report_top_customers(ADMIN_ID, []) == {"status": "error"}
        assert "❌" in text(env)

    def test_an_invalid_period_shows_the_usage(self, env):
        assert env.handler.handle_report_top_customers(ADMIN_ID, ["vorig-jaar"]) == {"status": "invalid_args"}
        assert "vorig-jaar" in text(env)
        assert "/report_top_customers [periode]" in text(env)
        env.db.get_events_by_type.assert_not_called()

    def test_a_start_date_in_the_future_is_refused(self, env):
        future = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")

        assert env.handler.handle_report_top_customers(ADMIN_ID, [future]) == {"status": "invalid_args"}
        assert "toekomst" in text(env)


class TestSalesByPeriod:
    def test_per_month_by_default_with_every_month_of_the_year(self, env):
        env.db.get_events_by_type.return_value = [
            payment("c1", "20", datetime(2025, 3, 3, tzinfo=UTC), "ORDER_CREATED"),
            payment("c2", "10", datetime(2025, 3, 20, tzinfo=UTC), "ORDER_CREATED"),
            payment("c1", "5", datetime(2025, 7, 1, 12, tzinfo=UTC), "ORDER_CREATED"),
        ]

        assert env.handler.handle_report_sales_by_period(ADMIN_ID, ["2025"]) == {"status": "success"}

        assert env.db.get_events_by_type.call_args.args[0] == "ORDER_CREATED"
        rows = re.findall(r"(?:^|<pre>)(jan|feb|mrt|apr|mei|jun|jul|aug|sep|okt|nov|dec) 2025", text(env), re.MULTILINE)
        assert len(rows) == 12
        report = text(env)
        assert re.search(r"mrt 2025\s+2× €\s+30\.00 █{10}", report)
        assert re.search(r"jul 2025\s+1× €\s+5\.00 █{2}", report)
        assert re.search(r"^feb 2025\s+–$", report, re.MULTILINE)  # a month without sales
        assert "Beste: mrt 2025 (2×, €30.00)" in report
        assert "Totaal: <b>3×</b>, <b>€35.00</b>" in report

    def test_paid_reports_payments_received(self, env):
        env.handler.handle_report_sales_by_period(ADMIN_ID, ["betaald"])

        assert env.db.get_events_by_type.call_args.args[0] == "PAYMENT_RECEIVED"

    def test_weeks_are_iso_weeks(self, env):
        env.db.get_events_by_type.return_value = [payment("c1", "20", datetime(2026, 1, 7, 12, tzinfo=UTC))]

        env.handler.handle_report_sales_by_period(ADMIN_ID, ["2026-01-01", "2026-01-31", "week"])

        report = text(env)
        assert "Verkopen per week" in report
        assert re.search(r"2026-W02\s+1×", report)
        assert re.search(r"2026-W01\s+–", report)  # the week of 1 January, also without sales

    def test_words_may_come_in_any_order(self, env):
        env.handler.handle_report_sales_by_period(ADMIN_ID, ["dag", "2026-01-01", "paid"])

        event_type, start, _ = env.db.get_events_by_type.call_args.args
        assert event_type == "PAYMENT_RECEIVED" and start.month == 1

    def test_days_over_a_long_period_list_only_days_with_sales(self, env):
        env.db.get_events_by_type.return_value = [payment("c1", "20", datetime(2025, 6, 2, 12, tzinfo=UTC))]

        env.handler.handle_report_sales_by_period(ADMIN_ID, ["2025", "day"])

        report = text(env)
        assert re.findall(r"(?:^|<pre>)(2025-\d\d-\d\d) ", report, re.MULTILINE) == ["2025-06-02"]
        assert "Alleen perioden met verkopen" in report

    def test_no_sales(self, env):
        assert env.handler.handle_report_sales_by_period(ADMIN_ID, []) == {"status": "no_data"}
        assert "Geen verkopen" in text(env)

    @pytest.mark.parametrize("args", [["2025"], ["2025", "paid"]])
    def test_orders_and_payments_of_an_excluded_customer_are_not_counted(self, env, args):
        env.db.get_events_by_type.return_value = [
            payment("c1", "20", datetime(2025, 3, 3, tzinfo=UTC)),
            payment(EXCLUDED, "500", datetime(2025, 3, 4, tzinfo=UTC)),
            payment(EXCLUDED, "300", datetime(2025, 7, 1, 12, tzinfo=UTC)),
        ]

        assert env.handler.handle_report_sales_by_period(ADMIN_ID, args) == {"status": "success"}

        report = text(env)
        assert re.search(r"mrt 2025\s+1× €\s+20\.00", report)
        assert re.search(r"^jul 2025\s+–$", report, re.MULTILINE)
        assert "Totaal: <b>1×</b>, <b>€20.00</b>" in report
        assert "Beste: mrt 2025 (1×, €20.00)" in report

    def test_only_sales_of_an_excluded_customer_is_no_data(self, env):
        env.db.get_events_by_type.return_value = [payment(EXCLUDED, "500", event_type="ORDER_CREATED")]

        assert env.handler.handle_report_sales_by_period(ADMIN_ID, []) == {"status": "no_data"}
        assert "Geen verkopen" in text(env)

    def test_invalid_period(self, env):
        assert env.handler.handle_report_sales_by_period(ADMIN_ID, ["2025", "2026", "2027"]) == {
            "status": "invalid_args"
        }
        assert "/report_sales_by_period" in text(env)

    def test_failed_read(self, env):
        env.db.get_events_by_type.side_effect = RuntimeError("boom")

        assert env.handler.handle_report_sales_by_period(ADMIN_ID, []) == {"status": "error"}

    def test_a_long_report_is_split_into_messages_that_fit(self, env):
        start = datetime(2024, 1, 1, 12, tzinfo=UTC)
        env.db.get_events_by_type.return_value = [
            payment("c1", "12.34", start + timedelta(days=day), "ORDER_CREATED") for day in range(366)
        ]

        env.handler.handle_report_sales_by_period(ADMIN_ID, ["2024", "day"])

        messages = sent(env)
        assert len(messages) > 1
        for message in messages:
            assert len(message) <= MESSAGE_LIMIT
            assert message.count("<pre>") == message.count("</pre>")
        assert len(re.findall(r"(?:^|<pre>)2024-\d\d-\d\d ", "\n".join(messages), re.MULTILINE)) == 366
        assert "Totaal" in messages[-1]


class TestCustomerReport:
    def _jan(self, env):
        jan = customer("11111111-aaaa", "Jan", "Jansen", "jantje")
        known_customers(env, jan)
        return jan

    def test_paid_per_month_and_open_amount(self, env):
        jan = self._jan(env)
        env.db.get_order_history_by_customer.return_value = [
            payment(jan.customer_id, "12.50", datetime(2025, 2, 3, 12, tzinfo=UTC)),
            payment(jan.customer_id, "99.00", datetime(2025, 2, 4, 12, tzinfo=UTC), "ORDER_CREATED"),
            payment(jan.customer_id, "7.50", datetime(2025, 5, 3, 12, tzinfo=UTC)),
        ]
        prices = {"pending": "10", "awaiting_payment": "5.25", "completed": "50", "cancelled": "8"}
        env.db.get_orders_by_customer.return_value = [
            Order(customer_id=jan.customer_id, status=status, total_price=Decimal(price))
            for status, price in prices.items()
        ]

        assert env.handler.handle_report_customer(ADMIN_ID, ["jantje", "2025"]) == {"status": "success"}

        report = text(env)
        assert "Klantrapport: Jan J" in report and "Jansen" not in report
        assert re.search(r"feb 2025\s+1× €\s+12\.50", report)  # the order event is not a payment
        assert re.search(r"mei 2025\s+1× €\s+7\.50", report)
        assert "Totaal betaald: <b>€20.00</b> (2×)" in report
        assert "Openstaand bedrag (nu): <b>€15.25</b> (2 " in report
        customer_id, start, end = env.db.get_order_history_by_customer.call_args.args
        assert customer_id == jan.customer_id and start.year == end.year == 2025
        env.db.get_orders_by_customer.assert_called_once_with(jan.customer_id, strict=True)

    def test_an_excluded_customer_still_has_a_customer_report(self, env):
        known_customers(env, customer(EXCLUDED, "Piet", "Puk", "pietje"))
        env.db.get_order_history_by_customer.return_value = [payment(EXCLUDED, "500", datetime(2025, 2, 3, tzinfo=UTC))]

        assert env.handler.handle_report_customer(ADMIN_ID, ["pietje", "2025"]) == {"status": "success"}

        assert "Totaal betaald: <b>€500.00</b> (1×)" in text(env)

    def test_nothing_paid_and_nothing_open(self, env):
        self._jan(env)

        env.handler.handle_report_customer(ADMIN_ID, ["jan"])

        assert "Geen betalingen" in text(env)
        assert "Openstaand bedrag (nu): geen" in text(env)

    def test_a_name_of_several_words(self, env):
        self._jan(env)

        assert env.handler.handle_report_customer(ADMIN_ID, ["jan", "jansen"]) == {"status": "success"}

    def test_several_matches_ask_which_customer_with_the_period_on_the_button(self, env):
        known_customers(env, customer("aaaaaaaa-1111-4111-8111-111111111111", "Jan", "A"), customer("b2", "Jan", "B"))

        result = env.handler.handle_report_customer(ADMIN_ID, ["jan", "2025-01-01", "2025-03-31"])

        assert result == {"status": "disambiguation_shown"}
        keyboard = env.handler._send_message.call_args.kwargs["reply_markup"]["inline_keyboard"]
        callbacks = [row[0]["callback_data"] for row in keyboard]
        assert callbacks[:2] == [
            "rptc_20250101-20250331_aaaaaaaa-1111-4111-8111-111111111111",
            "rptc_20250101-20250331_b2",
        ]
        assert all(len(data.encode()) <= 64 for data in callbacks)
        env.db.get_events_by_type.assert_not_called()

    def test_the_choice_shows_the_report_of_that_period(self, env):
        jan = self._jan(env)

        assert env.handler.handle_report_customer_select(ADMIN_ID, jan.customer_id, "20250101-20250331") == {
            "status": "success"
        }
        assert "2025-01-01 – 2025-03-31" in text(env)

    def test_the_choice_of_a_customer_that_is_gone(self, env):
        assert env.handler.handle_report_customer_select(ADMIN_ID, "gone-1234567", "20250101-20250331") == {
            "status": "user_not_found"
        }

    def test_a_broken_button(self, env):
        assert env.handler.handle_report_customer_select(ADMIN_ID, "c1", "garbage") == {"status": "invalid_args"}

    def test_unknown_customer(self, env):
        assert env.handler.handle_report_customer(ADMIN_ID, ["nobody"]) == {"status": "user_not_found"}
        assert "nobody" in text(env)

    def test_no_customer_shows_the_usage(self, env):
        assert env.handler.handle_report_customer(ADMIN_ID, ["2025"]) == {"status": "invalid_args"}
        assert "/report_customer" in text(env)

    def test_an_invalid_period_is_reported_before_looking_up_the_customer(self, env):
        assert env.handler.handle_report_customer(ADMIN_ID, ["jan", "2025-02-30"]) == {"status": "invalid_args"}
        env.db.get_customers_by_status.assert_not_called()

    @pytest.mark.parametrize("failing", ["get_order_history_by_customer", "get_orders_by_customer"])
    def test_a_failed_read_is_an_error(self, env, failing):
        self._jan(env)
        getattr(env.db, failing).side_effect = RuntimeError("boom")

        assert env.handler.handle_report_customer(ADMIN_ID, ["jan"]) == {"status": "error"}


class TestEnglish:
    def test_an_admin_with_english_gets_english_month_names(self, env):
        env.db.get_customer_by_telegram_id.return_value = Mock(language="en")
        env.db.get_events_by_type.return_value = [payment("c1", "20", datetime(2025, 5, 3, 12, tzinfo=UTC))]

        env.handler.handle_report_sales_by_period(ADMIN_ID, ["2025"])

        assert "Sales per month" in text(env)
        assert re.search(r"May 2025\s+1×", text(env))
