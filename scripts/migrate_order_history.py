#!/usr/bin/env python3
"""
One-time migration of the order-history table to the slim purchase-analytics
schema (see the "reduce order history to purchase analytics events" refactor).

For every item in ubbc-bot-<env>-order-history it will:

  1. DELETE rows whose event_type is not ORDER_CREATED or PAYMENT_RECEIVED
     (cancellations, price changes, generic status changes — no longer kept).
  2. For kept rows, REMOVE the dropped attributes:
     customer_name, order_id, changed_by, field_name, old_value, new_value,
     reason, customer_event, event_date, customer_name_event.
  3. Backfill `amount` on ORDER_CREATED rows that lack it, when the legacy
     new_value carried a "total=<n>" (e.g. "quantity=2, total=24.00").
     PAYMENT_RECEIVED rows already carry `amount`.

The script is idempotent: once a table is clean, a re-run makes no changes.

Safety:
  - Dry-run by default. Pass --apply to actually write.
  - Run this ONLY after the new event-time-index GSI is ACTIVE and the slim
    write rules are deployed, so no process is still writing the old shape.

Usage:
    python scripts/migrate_order_history.py <test|prod> [--apply]
"""

import sys
from decimal import Decimal, InvalidOperation

import boto3

KEEP_EVENT_TYPES = {"ORDER_CREATED", "PAYMENT_RECEIVED"}

# Attributes the slim schema no longer stores.
DROPPED_ATTRS = [
    "customer_name",
    "order_id",
    "changed_by",
    "field_name",
    "old_value",
    "new_value",
    "reason",
    "customer_event",
    "event_date",
    "customer_name_event",
]


def _parse_total(new_value) -> Decimal | None:
    """Extract the total amount from a legacy new_value like 'quantity=2, total=24.00'."""
    if not isinstance(new_value, str) or "total=" not in new_value:
        return None
    try:
        raw = new_value.split("total=", 1)[1].strip().rstrip(",")
        return Decimal(raw)
    except IndexError, InvalidOperation:
        return None


def migrate(environment: str, do_apply: bool):
    dynamodb = boto3.resource("dynamodb")
    table_name = f"ubbc-bot-{environment}-order-history"
    table = dynamodb.Table(table_name)

    mode = "APPLY" if do_apply else "DRY-RUN"
    print(f"[{mode}] Migrating {table_name}\n")

    scanned = deleted = stripped = backfilled = unchanged = 0

    scan_kwargs: dict = {}
    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            scanned += 1
            history_id = item["history_id"]
            event_type = item.get("event_type", "")

            # 1. Delete non-purchase events.
            if event_type not in KEEP_EVENT_TYPES:
                print(f"  DELETE {history_id} (event_type={event_type or 'MISSING'})")
                if do_apply:
                    table.delete_item(Key={"history_id": history_id})
                deleted += 1
                continue

            # 2/3. Build REMOVE + SET for kept rows.
            to_remove = [a for a in DROPPED_ATTRS if a in item]

            amount_set = None
            if event_type == "ORDER_CREATED" and item.get("amount") is None:
                amount_set = _parse_total(item.get("new_value"))

            if not to_remove and amount_set is None:
                unchanged += 1
                continue

            parts = []
            expr_names = {}
            expr_values = {}
            if amount_set is not None:
                parts.append("SET #amount = :amount")
                expr_names["#amount"] = "amount"
                expr_values[":amount"] = amount_set
            if to_remove:
                parts.append("REMOVE " + ", ".join(f"#{a}" for a in to_remove))
                expr_names.update({f"#{a}": a for a in to_remove})

            update_expr = " ".join(parts)
            desc = []
            if to_remove:
                desc.append(f"strip {to_remove}")
                stripped += 1
            if amount_set is not None:
                desc.append(f"amount={amount_set}")
                backfilled += 1
            print(f"  UPDATE {history_id} ({event_type}): {'; '.join(desc)}")

            if do_apply:
                kwargs = {"Key": {"history_id": history_id}, "UpdateExpression": update_expr}
                if expr_names:
                    kwargs["ExpressionAttributeNames"] = expr_names
                if expr_values:
                    kwargs["ExpressionAttributeValues"] = expr_values
                table.update_item(**kwargs)

        if "LastEvaluatedKey" in response:
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        else:
            break

    print("\nSummary:")
    print(f"  Scanned:    {scanned}")
    print(f"  Deleted:    {deleted} (non-purchase events)")
    print(f"  Stripped:   {stripped} (dropped attributes removed)")
    print(f"  Backfilled: {backfilled} (amount derived on ORDER_CREATED)")
    print(f"  Unchanged:  {unchanged}")
    if not do_apply:
        print("\nDRY-RUN only — no writes made. Re-run with --apply to perform the migration.")


if __name__ == "__main__":
    args = sys.argv[1:]
    do_apply = "--apply" in args
    args = [a for a in args if a != "--apply"]
    if len(args) != 1 or args[0] not in ("test", "prod"):
        print("Usage: python scripts/migrate_order_history.py <test|prod> [--apply]")
        sys.exit(1)
    migrate(args[0], do_apply)
    print("\nDone.")
