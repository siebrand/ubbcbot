"""Personal data export (right of access / data portability).

Builds a zip with JSON files holding everything the bot stores about one customer. The export is
limited to once per 30 days per customer, claimed atomically on the customer record
(``last_data_export_at``). It contains only the customer's own data: other customers' names, and
the identity of the administrator behind a credit transaction, are left out.
"""

import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from models.entities import Customer

DATA_EXPORT_MIN_INTERVAL_SECONDS = 30 * 24 * 60 * 60

# Amounts are written as text with two decimals so no precision is lost
MONEY_FIELDS = frozenset(
    {
        "unit_price",
        "total_price",
        "amount",
        "balance_before",
        "balance_after",
        "current_balance",
        "total_credits_issued",
        "total_credits_used",
    }
)

# Fields that identify someone else (the administrator who made a credit transaction)
OMITTED_TRANSACTION_FIELDS = frozenset({"created_by"})


def _clean(value: Any, key: str | None = None) -> Any:
    """Make a value JSON friendly: DynamoDB Decimals, datetimes and nested containers"""
    if isinstance(value, Decimal):
        if key in MONEY_FIELDS:
            return f"{value:.2f}"
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _clean(v, k) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def _epoch_to_iso(value: Any) -> str | None:
    return datetime.fromtimestamp(int(value), UTC).isoformat() if value is not None else None


class DataExportService:
    def __init__(self, db, translate: Callable[..., str]):
        """``translate(key, **params)`` returns text in the customer's language"""
        self.db = db
        self._translate = translate

    def collect(self, customer: Customer) -> dict[str, Any]:
        """Gather everything stored about the customer, grouped per output file"""
        customer_id = customer.customer_id

        profile = asdict(customer)
        profile["last_data_export_at"] = _epoch_to_iso(customer.last_data_export_at)

        offer_names: dict[int, str | None] = {}
        orders = []
        for order in sorted(self.db.get_orders_by_customer(customer_id), key=lambda o: str(o.created_at)):
            if order.offer_id not in offer_names:
                offer = self.db.get_offer(order.offer_id)
                offer_names[order.offer_id] = offer.name if offer else None
            entry = asdict(order)
            entry["offer_name"] = offer_names[order.offer_id]
            orders.append(entry)

        credit = self.db.get_customer_credit(customer_id)
        transactions = [
            {k: v for k, v in asdict(t).items() if k not in OMITTED_TRANSACTION_FIELDS}
            for t in self.db.get_all_credit_transactions_by_customer(customer_id)
        ]

        history = []
        for event in self.db.get_order_history_by_customer(customer_id):
            entry = asdict(event)
            entry["delete_after"] = _epoch_to_iso(entry.pop("ttl", None))
            history.append(entry)

        return {
            "profile": profile,
            "orders": orders,
            "credit": {"balance": asdict(credit) if credit else None, "transactions": transactions},
            "purchase_history": history,
        }

    def build_zip(self, customer: Customer, now: datetime | None = None) -> bytes:
        """Return the zip file (profile, orders, credit, purchase history and a README) as bytes"""
        now = now or datetime.now(UTC)
        data = self.collect(customer)
        readme = self._translate("data_export_readme", exported_at=now.isoformat(), customer_id=customer.customer_id)

        files = {
            "README.txt": readme,
            "profile.json": self._dump(data["profile"]),
            "orders.json": self._dump(data["orders"]),
            "credit.json": self._dump(data["credit"]),
            "purchase_history.json": self._dump(data["purchase_history"]),
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                info = zipfile.ZipInfo(name, date_time=now.timetuple()[:6])
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content.encode("utf-8"))
        return buffer.getvalue()

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(_clean(value), indent=2, ensure_ascii=False)
