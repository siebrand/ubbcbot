#!/usr/bin/env python3
"""
Revert an offer from delivered back to ordered status.

Fixes a mistaken delivery by:
1. Setting orders with status 'ready_for_labeling' back to 'ordered'
2. Setting received_quantity to 0 for those orders
3. Setting boxes from 'delivered' back to 'ordered'

USAGE:
    source test_env/bin/activate
    python3 scripts/revert_delivery_to_ordered.py <offer_id> [environment]

    # Examples:
    python3 scripts/revert_delivery_to_ordered.py 42
    python3 scripts/revert_delivery_to_ordered.py 42 prod

NOTE: Requires AWS credentials configured for DynamoDB access.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.database import DynamoDBService
from models.entities import BoxStatus, OrderStatus


def revert_delivery(offer_id: int, dry_run=True):
    db = DynamoDBService()

    # Get orders for this offer with status ready_for_labeling
    all_orders = db.get_orders_by_offer(offer_id)
    target_orders = [o for o in all_orders if o.status == OrderStatus.READY_FOR_LABELING.value]

    # Get delivered boxes for this offer
    all_boxes = db.get_boxes_by_offer(offer_id)
    delivered_boxes = [b for b in all_boxes if b.status == BoxStatus.DELIVERED.value]

    print(f"Offer {offer_id}:")
    print(f"  Orders to revert (ready_for_labeling → ordered): {len(target_orders)}")
    print(f"  Boxes to revert (delivered → ordered): {len(delivered_boxes)}")

    if not target_orders and not delivered_boxes:
        print("\n✅ Nothing to revert.")
        return 0

    # Revert orders
    order_count = 0
    for order in target_orders:
        action = "Would update" if dry_run else "Updating"
        print(f"  {action} order {order.order_id[:8]} (qty: {order.quantity}, received: {order.received_quantity} → 0)")
        if not dry_run:
            if db.update_order(order.order_id, {'status': OrderStatus.ORDERED.value, 'received_quantity': 0}):
                order_count += 1
            else:
                print(f"    ERROR: Failed to update order {order.order_id[:8]}")
        else:
            order_count += 1

    # Revert boxes
    box_count = 0
    for box in delivered_boxes:
        action = "Would update" if dry_run else "Updating"
        print(f"  {action} box {box.box_id[:8]} (delivered → ordered)")
        if not dry_run:
            if db.update_box(box.box_id, {'status': BoxStatus.ORDERED.value}):
                box_count += 1
            else:
                print(f"    ERROR: Failed to update box {box.box_id[:8]}")
        else:
            box_count += 1

    label = "DRY RUN: Would revert" if dry_run else "Reverted"
    print(f"\n{'📋' if dry_run else '✅'} {label} {order_count} orders and {box_count} boxes")
    return order_count + box_count


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/revert_delivery_to_ordered.py <offer_id> [environment]")
        sys.exit(1)

    offer_id = int(sys.argv[1])
    environment = sys.argv[2] if len(sys.argv) > 2 else 'test'

    if environment not in ['test', 'prod']:
        print("Error: Environment must be 'test' or 'prod'")
        sys.exit(1)

    os.environ['ENVIRONMENT'] = environment
    os.environ['DYNAMODB_TABLE_PREFIX'] = f'ubbc-bot-{environment}'

    print("=" * 60)
    print(f"Revert Delivery to Ordered - {environment.upper()} Environment")
    print(f"Offer ID: {offer_id}")
    print("=" * 60)

    # Dry run first
    print("\nRunning dry-run...\n")
    count = revert_delivery(offer_id, dry_run=True)

    if count == 0:
        sys.exit(0)

    response = input("\nApply changes? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)

    print("\nApplying changes...\n")
    revert_delivery(offer_id, dry_run=False)
    print("\nDone!")
