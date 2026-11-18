"""Admin reports on purchases: top customers, sales over time and one customer's payments and open amount.

Read-only. The order-history table holds only pseudonymous events (customer_id, amount, time); customer
names are looked up when the report is shown, in the public "Firstname L" format, and never logged.
See services/reporting.py for the periods and calculations.
"""

import logging
import random
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from handlers.base_handler import BaseHandler
from services import reporting
from services.reporting import MONTH, WEEK, Bucket, Period, PeriodError

logger = logging.getLogger()

# Telegram allows 4096 characters per message; leave room for the "TEST - " prefix and the <pre> tags
MESSAGE_LIMIT = 3900
NAME_WIDTH = 16
# Shown with the short id instead of a name when the customer record was deleted (right to be forgotten)
DELETED_MARK = "✗"
# More buckets than this are not all listed: only those with sales (a day-by-day year would be 365 lines)
MAX_FILLED_BUCKETS = 62


class ReportCommands(BaseHandler):
    # --- /report_top_customers [period] [anon] --------------------------------------------------------

    def handle_report_top_customers(self, chat_id: int, args: list) -> dict[str, Any]:
        """Customers ranked by the amount they paid in the period. With "anon": made-up names instead."""
        anon = any(word.lower() in reporting.ANON_WORDS for word in args)
        period_args = [word for word in args if word.lower() not in reporting.ANON_WORDS]
        period = self._period_or_error(chat_id, period_args, "usage_report_top_customers")
        if period is None:
            return {"status": "invalid_args"}

        events = self._read(self.db.get_events_by_type, "PAYMENT_RECEIVED", period.start, period.end, strict=True)
        if events is None:
            return self._report_failed(chat_id)
        events = reporting.without_excluded(events)

        header = [self._t("report_top_customers_title", chat_id), self._period_line(chat_id, period)]
        if not events:
            self._send_report(chat_id, header + ["", self._t("report_no_payments", chat_id)])
            return {"status": "no_data"}

        ranked = reporting.totals_per_customer(events)
        top = ranked[: reporting.TOP_CUSTOMERS_LIMIT]
        if anon:
            names = random.sample(reporting.ANON_NAMES, len(top))
        else:
            names = [self._report_name(t.customer_id, chat_id) for t in top]
        name_width = min(max(len(name) for name in names), NAME_WIDTH)
        amount_width = max(len(f"{t.amount:.2f}") for t in top)
        rows = [
            f"{place:>2}. {self._fit(name, name_width)} € {t.amount:>{amount_width}.2f}  {t.count}×"
            for place, (name, t) in enumerate(zip(names, top, strict=True), start=1)
        ]

        overall = reporting.total(events)
        footer = [
            self._t("report_total_paid", chat_id, amount=overall.amount, count=overall.count),
            self._t("report_customer_count", chat_id, customers=len(ranked)),
        ]
        if len(ranked) > len(top):
            footer.append(self._t("report_top_shown", chat_id, shown=len(top)))
        if any(name.startswith(DELETED_MARK) for name in names):
            footer.append(self._t("report_deleted_customer", chat_id, mark=DELETED_MARK))

        self._send_report(chat_id, header, rows, footer)
        return {"status": "success"}

    # --- /report_sales_by_period [period] [day|week|month] [paid] -----------------------------------

    def handle_report_sales_by_period(self, chat_id: int, args: list) -> dict[str, Any]:
        """Number of orders and their value per day, week or month. With "paid": payments received instead."""
        granularity = MONTH
        paid = False
        period_args = []
        for word in args:
            lowered = word.lower()
            if lowered in reporting.GRANULARITY_WORDS:
                granularity = reporting.GRANULARITY_WORDS[lowered]
            elif lowered in reporting.PAID_WORDS:
                paid = True
            else:
                period_args.append(word)

        period = self._period_or_error(chat_id, period_args, "usage_report_sales_by_period")
        if period is None:
            return {"status": "invalid_args"}

        event_type = "PAYMENT_RECEIVED" if paid else "ORDER_CREATED"
        events = self._read(self.db.get_events_by_type, event_type, period.start, period.end, strict=True)
        if events is None:
            return self._report_failed(chat_id)
        events = reporting.without_excluded(events)

        header = [
            self._t(f"report_sales_title_{granularity}", chat_id),
            self._period_line(chat_id, period),
            self._t("report_based_on_payments" if paid else "report_based_on_orders", chat_id),
        ]
        if not events:
            self._send_report(chat_id, header + ["", self._t("report_no_sales", chat_id)])
            return {"status": "no_data"}

        buckets = reporting.aggregate_by_bucket(events, granularity)
        starts = reporting.bucket_starts(period, granularity)
        if len(starts) > MAX_FILLED_BUCKETS:
            starts = sorted(buckets)
            header.append(self._t("report_empty_periods_hidden", chat_id))
        rows = self._bucket_rows(chat_id, starts, buckets, granularity)

        overall = reporting.total(events)
        peak_start = max(buckets, key=lambda start: (buckets[start].amount, buckets[start].count))
        peak = buckets[peak_start]
        footer = [
            self._t("report_sales_total", chat_id, count=overall.count, amount=overall.amount),
            self._t(
                "report_sales_peak",
                chat_id,
                label=self._bucket_label(chat_id, peak_start, granularity),
                count=peak.count,
                amount=peak.amount,
            ),
        ]

        self._send_report(chat_id, header, rows, footer)
        return {"status": "success"}

    # --- /report_customer <customer> [period] -----------------------------------------------------------

    def handle_report_customer(self, chat_id: int, args: list) -> dict[str, Any]:
        """One customer: paid per month in the period, and the amount of the orders not paid yet"""
        identifier_words, period_args = reporting.split_trailing_period(args)
        if not identifier_words:
            self._send_message(chat_id, self._t("usage_report_customer", chat_id))
            return {"status": "invalid_args"}

        period = self._period_or_error(chat_id, period_args, "usage_report_customer")
        if period is None:
            return {"status": "invalid_args"}

        identifier = " ".join(identifier_words)
        matches = self.validator.match_customers(identifier, self.validator.load_customers(None))
        if not matches:
            self._send_message(
                chat_id,
                self._t("user_not_found", chat_id, identifier=identifier),
                reply_markup=self._build_admin_menu_keyboard(),
            )
            return {"status": "user_not_found"}

        if len(matches) > 1:
            return self._choose_customer(chat_id, identifier, matches, period)

        return self._customer_report(chat_id, matches[0], period)

    def handle_report_customer_select(self, chat_id: int, customer_id: str, period_code: str) -> dict[str, Any]:
        """The admin picked one of several customers with the same name"""
        try:
            period = reporting.parse_period_code(period_code)
        except PeriodError:
            self._send_message(chat_id, self._t("invalid_format", chat_id))
            return {"status": "invalid_args"}

        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id[:8]))
            return {"status": "user_not_found"}

        return self._customer_report(chat_id, customer, period)

    def _choose_customer(self, chat_id: int, identifier: str, matches: list, period: Period) -> dict[str, Any]:
        """Ask which customer is meant. The button carries the period, so the choice shows the same report."""
        buttons = []
        for customer in matches[:10]:
            name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            username = f" (@{customer.username})" if customer.username else ""
            buttons.append(
                [{"text": f"📊 {name}{username}", "callback_data": f"rptc_{period.code}_{customer.customer_id}"}]
            )
        buttons.append([{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}])

        self._send_message(
            chat_id,
            self._t("report_choose_customer", chat_id, identifier=identifier),
            reply_markup={"inline_keyboard": buttons},
        )
        return {"status": "disambiguation_shown"}

    def _customer_report(self, chat_id: int, customer, period: Period) -> dict[str, Any]:
        customer_id = customer.customer_id
        history = self._read(self.db.get_order_history_by_customer, customer_id, period.start, period.end)
        orders = self._read(self.db.get_orders_by_customer, customer_id, strict=True)
        if history is None or orders is None:
            return self._report_failed(chat_id)

        payments = [event for event in history if event.event_type == "PAYMENT_RECEIVED"]
        header = [
            self._t("report_customer_title", chat_id, name=self._get_public_name(customer)),
            self._period_line(chat_id, period),
            "",
            self._t("report_paid_per_month", chat_id),
        ]

        rows: list[str] = []
        if payments:
            buckets = reporting.aggregate_by_bucket(payments, MONTH)
            rows = self._bucket_rows(chat_id, reporting.bucket_starts(period, MONTH), buckets, MONTH)
            paid = reporting.total(payments)
            footer = [self._t("report_total_paid", chat_id, amount=paid.amount, count=paid.count)]
        else:
            footer = [self._t("report_no_payments", chat_id)]

        unpaid = reporting.open_orders(orders)
        footer.append("")
        if unpaid:
            amount = sum((order.total_price or Decimal("0") for order in unpaid), Decimal("0"))
            footer.append(self._t("report_open_amount", chat_id, amount=amount, count=len(unpaid)))
        else:
            footer.append(self._t("report_open_amount_none", chat_id))

        self._send_report(chat_id, header, rows, footer)
        return {"status": "success"}

    # --- shared ---------------------------------------------------------------------------------------

    def _period_or_error(self, chat_id: int, args: list, usage_key: str) -> Period | None:
        """The period of the arguments, or None after telling the admin what is wrong"""
        try:
            return reporting.parse_period(args)
        except PeriodError as e:
            key = "report_future_date" if e.reason == "future" else "report_invalid_period"
            message = self._t(key, chat_id, value=e.value) + "\n\n" + self._t(usage_key, chat_id)
            self._send_message(chat_id, message)
            return None

    @staticmethod
    def _read(query: Callable[..., Any], *args, **kwargs) -> Any:
        """Run a database read; None when it failed, so a report never shows "nothing" after an error"""
        try:
            return query(*args, **kwargs)
        except Exception as e:
            logger.error(f"Report: reading the data failed: {e}")
            return None

    def _report_failed(self, chat_id: int) -> dict[str, Any]:
        self._send_message(chat_id, self._t("report_failed", chat_id))
        return {"status": "error"}

    def _period_line(self, chat_id: int, period: Period) -> str:
        return self._t("report_period", chat_id, start=period.first_day.isoformat(), end=period.last_day.isoformat())

    def _report_name(self, customer_id: str, chat_id: int) -> str:
        """Public name of a customer (not escaped), or the mark and the short id when the record is gone"""
        customer = self.db.get_customer(customer_id)
        if customer is None:
            return f"{DELETED_MARK} {customer_id[:8]}"
        parts = [customer.first_name] if customer.first_name else []
        if customer.last_name:
            parts.append(customer.last_name[0])
        return " ".join(parts) or customer.username or self._t("unknown", chat_id)

    @staticmethod
    def _fit(text: str, width: int) -> str:
        """Pad or cut a name to the column width of the table"""
        if len(text) > width:
            return text[: width - 1] + "…"
        return text.ljust(width)

    def _bucket_label(self, chat_id: int, start: date, granularity: str) -> str:
        """ISO-8601 for days (2026-11-18) and weeks (2026-W47), a short month name for months (nov 2026)"""
        if granularity == MONTH:
            months = self._t("report_month_names", chat_id).split(",")
            return f"{months[start.month - 1]} {start.year}"
        if granularity == WEEK:
            year, week, _ = start.isocalendar()
            return f"{year}-W{week:02d}"
        return f"{start:%Y-%m-%d}"

    def _bucket_rows(self, chat_id: int, starts: list[date], buckets: dict[date, Bucket], granularity: str) -> list:
        """One line per bucket: label, count, amount and a bar relative to the best bucket. Empty buckets: a dash."""
        largest = max((bucket.amount for bucket in buckets.values()), default=Decimal("0"))
        amount_width = max([len(f"{b.amount:.2f}") for b in buckets.values()] + [4])
        count_width = max([len(str(b.count)) for b in buckets.values()] + [1])
        label_width = 8 if granularity in (MONTH, WEEK) else 10
        rows = []
        for start in starts:
            label = self._bucket_label(chat_id, start, granularity).ljust(label_width)
            bucket = buckets.get(start)
            if bucket is None:
                rows.append(f"{label} {'–':>{count_width + 1}}")
                continue
            rows.append(
                f"{label} {bucket.count:>{count_width}}× € {bucket.amount:>{amount_width}.2f} "
                f"{reporting.bar(bucket.amount, largest)}".rstrip()
            )
        return rows

    def _send_report(self, chat_id: int, header: list[str], rows: list[str] | None = None, footer=None) -> None:
        """Send a report as HTML: header, the rows as a monospace table, footer. Split over messages if too long.

        Header and footer lines are translations (HTML); table rows are escaped in _table_chunks.
        """
        pieces = ["\n".join(header)]
        if rows:
            pieces.extend(self._table_chunks(rows))
        if footer:
            pieces.append("\n".join(footer))

        messages: list[str] = []
        for piece in pieces:
            if messages and len(messages[-1]) + 2 + len(piece) <= MESSAGE_LIMIT:
                messages[-1] += "\n\n" + piece
            else:
                messages.append(piece)

        for message in messages:
            self._send_message(chat_id, message, parse_mode="HTML")

    def _table_chunks(self, rows: list[str]) -> list[str]:
        """The rows as <pre> blocks that each fit in a message (escaped: rows hold customer names)"""
        chunks: list[str] = []
        current: list[str] = []
        size = len("<pre></pre>")
        for row in rows:
            line = self._escape_html(row)
            if current and size + len(line) + 1 > MESSAGE_LIMIT:
                chunks.append("<pre>" + "\n".join(current) + "</pre>")
                current, size = [], len("<pre></pre>")
            current.append(line)
            size += len(line) + 1
        if current:
            chunks.append("<pre>" + "\n".join(current) + "</pre>")
        return chunks
