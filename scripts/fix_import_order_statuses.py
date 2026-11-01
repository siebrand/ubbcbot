#!/usr/bin/env python3
"""
Fix order statuses for imported orders where boxes are ORDERED but orders are still PENDING.
This corrects data inconsistency from the import bug.

USAGE:
    # Activate existing virtual environment and install dependencies
    source test_env/bin/activate
    pip install "botocore[crt]"

    # Run the script (defaults to test environment)
    python3 scripts/fix_import_order_statuses.py

    # Or specify environment
    python3 scripts/fix_import_order_statuses.py test
    python3 scripts/fix_import_order_statuses.py prod

The script will:
1. Run a dry-run to identify inconsistent orders
2. Show detailed report of what needs fixing
3. Ask for confirmation before applying changes
4. Update order statuses from 'pending' to 'ordered'

NOTE: Requires AWS credentials configured for DynamoDB access.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models.entities import BoxStatus
from services.database import DynamoDBService


def fix_import_order_statuses(dry_run=True):
    """Update pending orders to ordered when their box is ordered"""
    db = DynamoDBService()

    # Get all ORDERED boxes
    all_boxes = db.get_all_boxes()
    ordered_boxes = [b for b in all_boxes if b.status == BoxStatus.ORDERED.value]

    print(f"Found {len(ordered_boxes)} ORDERED boxes")

    fixed_count = 0
    issues = []

    for box in ordered_boxes:
        # Get orders in this box
        orders = db.get_orders_by_box(box.box_id)
        pending_orders = [o for o in orders if o.status == "pending"]

        if pending_orders:
            print(f"\nBox {box.box_id[:8]} (Offer {box.offer_id}):")
            print(f"  Found {len(pending_orders)} pending orders in ORDERED box")

            for order in pending_orders:
                customer = db.get_customer(order.customer_id)
                customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Unknown"

                action = "Would update" if dry_run else "Updating"
                print(f"  - {action} order {order.order_id[:8]} ({customer_name})")

                issues.append(
                    {
                        "box_id": box.box_id[:8],
                        "offer_id": box.offer_id,
                        "order_id": order.order_id[:8],
                        "customer": customer_name,
                    }
                )

                if not dry_run:
                    if db.update_order(order.order_id, {"status": "ordered"}):
                        fixed_count += 1
                    else:
                        print(f"    ERROR: Failed to update order {order.order_id[:8]}")
                else:
                    fixed_count += 1

    if dry_run:
        print(f"\n📋 DRY RUN: Would fix {fixed_count} orders")
    else:
        print(f"\n✅ Fixed {fixed_count} orders")

    return fixed_count, issues


if __name__ == "__main__":
    # Parse environment argument
    environment = sys.argv[1] if len(sys.argv) > 1 else "test"

    if environment not in ["test", "prod"]:
        print("Error: Environment must be 'test' or 'prod'")
        sys.exit(1)

    # Set environment variables for DynamoDBService
    os.environ["ENVIRONMENT"] = environment
    os.environ["DYNAMODB_TABLE_PREFIX"] = f"ubbc-bot-{environment}"

    print("=" * 60)
    print(f"Fix Import Order Statuses Script - {environment.upper()} Environment")
    print(f"Table Prefix: ubbc-bot-{environment}")
    print("=" * 60)
    print("\nThis script will update orders from 'pending' to 'ordered'")
    print("when their box status is already 'ordered'.\n")

    # Run dry-run first
    print("Running dry-run to identify issues...\n")
    count, issues = fix_import_order_statuses(dry_run=True)

    if count == 0:
        print("\n✅ No issues found. All orders are consistent.")
        sys.exit(0)

    print(f"\n⚠️  Found {count} orders that need fixing.")
    response = input("\nApply fixes? (yes/no): ")

    if response.lower() != "yes":
        print("Aborted.")
        sys.exit(0)

    print("\nApplying fixes...\n")
    fixed, _ = fix_import_order_statuses(dry_run=False)
    print(f"\nDone! Fixed {fixed} orders.")
