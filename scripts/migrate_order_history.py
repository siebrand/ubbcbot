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

import contextlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation

import boto3

KEEP_EVENT_TYPES = {"ORDER_CREATED", "PAYMENT_RECEIVED"}

# The only attributes the slim schema keeps. Anything else on a row is a legacy
# attribute and is removed (allow-list, so forgotten legacy fields such as
# triggers_refund / changed_by / composite keys are all cleaned up).
KEEP_ATTRS = {
    "history_id",
    "customer_id",
    "offer_name",
    "event_type",
    "changed_at",
    "amount",
    "ttl",
}


def _parse_total(new_value) -> Decimal | None:
    """Extract the total amount from a legacy new_value like 'quantity=2, total=24.00'."""
    if not isinstance(new_value, str) or "total=" not in new_value:
        return None
    try:
        raw = new_value.split("total=", 1)[1].strip().rstrip(",")
        return Decimal(raw)
    except IndexError, InvalidOperation:
        return None


def _build_update(item):
    """Return (update_expr, expr_names, expr_values, did_strip, did_backfill) for a
    kept row, or None if the row is already clean."""
    event_type = item.get("event_type", "")
    to_remove = sorted(a for a in item if a not in KEEP_ATTRS)

    amount_set = None
    if event_type == "ORDER_CREATED" and item.get("amount") is None:
        amount_set = _parse_total(item.get("new_value"))

    if not to_remove and amount_set is None:
        return None

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

    return " ".join(parts), expr_names, expr_values, bool(to_remove), amount_set is not None


def migrate(environment: str, do_apply: bool, workers: int = 32):
    from botocore.config import Config

    # Size the HTTP connection pool to the worker count so concurrent update_item
    # calls do not queue behind the default pool of 10.
    dynamodb = boto3.resource("dynamodb", config=Config(max_pool_connections=max(workers, 10)))
    table_name = f"ubbc-bot-{environment}-order-history"
    table = dynamodb.Table(table_name)

    mode = "APPLY" if do_apply else "DRY-RUN"
    print(f"[{mode}] Migrating {table_name} (workers={workers})\n")

    scanned = deleted = stripped = backfilled = unchanged = 0
    update_jobs = []  # (key, update_expr, expr_names, expr_values)

    # Batched deletes via BatchWriteItem (25/op, auto-retry). Only used with --apply.
    writer_cm = table.batch_writer() if do_apply else contextlib.nullcontext()
    with writer_cm as writer:
        scan_kwargs: dict = {}
        while True:
            response = table.scan(**scan_kwargs)
            for item in response.get("Items", []):
                scanned += 1
                if scanned % 500 == 0:
                    print(f"  ... scanned {scanned} records")
                history_id = item["history_id"]
                event_type = item.get("event_type", "")

                # 1. Delete non-purchase events (batched).
                if event_type not in KEEP_EVENT_TYPES:
                    if do_apply:
                        writer.delete_item(Key={"history_id": history_id})
                    deleted += 1
                    continue

                # 2/3. Strip legacy attributes / backfill amount on kept rows.
                plan = _build_update(item)
                if plan is None:
                    unchanged += 1
                    continue
                update_expr, expr_names, expr_values, did_strip, did_backfill = plan
                if did_strip:
                    stripped += 1
                if did_backfill:
                    backfilled += 1
                if do_apply:
                    update_jobs.append(({"history_id": history_id}, update_expr, expr_names, expr_values))

            if "LastEvaluatedKey" in response:
                scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            else:
                break
    # (batch_writer flushes any remaining deletes on context exit)

    # Updates can't be batched (BatchWriteItem has no partial-update op), so run
    # them concurrently to hide per-request latency.
    if do_apply and update_jobs:
        print(f"\n  Applying {len(update_jobs)} updates with {workers} workers...")

        def _apply(job):
            key, update_expr, expr_names, expr_values = job
            kwargs = {"Key": key, "UpdateExpression": update_expr}
            if expr_names:
                kwargs["ExpressionAttributeNames"] = expr_names
            if expr_values:
                kwargs["ExpressionAttributeValues"] = expr_values
            table.update_item(**kwargs)

        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for _ in as_completed([pool.submit(_apply, j) for j in update_jobs]):
                done += 1
                if done % 500 == 0:
                    print(f"  ... updated {done}/{len(update_jobs)}")

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

    workers = 32
    for a in list(args):
        if a.startswith("--workers="):
            workers = int(a.split("=", 1)[1])
            args.remove(a)

    if len(args) != 1 or args[0] not in ("test", "prod"):
        print("Usage: python scripts/migrate_order_history.py <test|prod> [--apply] [--workers=N]")
        sys.exit(1)
    migrate(args[0], do_apply, workers)
    print("\nDone.")
