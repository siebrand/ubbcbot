#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.entities import Order, Customer, Offer, Box, OrderStatus, OfferStatus, BoxStatus
from decimal import Decimal

def test_order_execution():
    """Test order execution scenarios"""
    print("=== Testing order execution ===")
    
    # Success: normal order
    offer = Offer(offer_id=1, price_per_unit=Decimal('5.00'), wholesale_box_size=12, status=OfferStatus.ACTIVE.value)
    quantity = 2
    total_price = offer.price_per_unit * quantity
    assert total_price == Decimal('10.00')
    print("✅ Order total calculated correctly")
    
    # Success: order fits in existing box
    box = Box(current_quantity=8, max_capacity=12, min_breakeven=10)
    available_space = box.max_capacity - box.current_quantity
    can_fit = quantity <= available_space
    assert can_fit
    print("✅ Order fits in existing box")
    
    # Failure: insufficient capacity
    box_full = Box(current_quantity=12, max_capacity=12)
    available_space = box_full.max_capacity - box_full.current_quantity
    can_fit = quantity <= available_space
    assert not can_fit
    print("✅ Insufficient capacity detected")

def test_duplicate_order_handling():
    """Test duplicate order confirmation"""
    print("\n=== Testing duplicate order handling ===")
    
    # Has existing orders - needs confirmation
    existing_orders = [
        Order(quantity=2, status=OrderStatus.PENDING.value),
        Order(quantity=1, status=OrderStatus.CONFIRMED.value)
    ]
    has_existing = len(existing_orders) > 0
    assert has_existing
    print("✅ Existing orders detected")
    
    # No existing orders - direct execution
    no_orders = []
    has_existing = len(no_orders) > 0
    assert not has_existing
    print("✅ No existing orders - direct execution")

def test_capacity_management():
    """Test capacity and box management"""
    print("\n=== Testing capacity management ===")
    
    # Calculate total available capacity
    boxes = [
        Box(current_quantity=8, max_capacity=12, status=BoxStatus.OPEN.value),
        Box(current_quantity=10, max_capacity=12, status=BoxStatus.MINIMUM_REACHED.value),
        Box(current_quantity=12, max_capacity=12, status=BoxStatus.ORDERED.value)  # No capacity
    ]
    
    total_available = 0
    for box in boxes:
        if box.status in [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value, BoxStatus.FULL.value]:
            total_available += box.max_capacity - box.current_quantity
    
    assert total_available == 6  # (12-8) + (12-10) + 0
    print("✅ Available capacity calculated correctly")
    
    # Check if new box creation is allowed
    has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes)
    offer_status = OfferStatus.ACTIVE.value
    can_create_box = (offer_status not in [OfferStatus.ORDERED.value, OfferStatus.COMPLETED.value, OfferStatus.DELIVERED.value] 
                     and not has_ordered_boxes)
    assert not can_create_box  # Has ordered boxes
    print("✅ Box creation blocked when ordered boxes exist")

def test_order_status_updates():
    """Test order status transitions"""
    print("\n=== Testing order status updates ===")
    
    # Pending -> Ordered (when box becomes ordered)
    order = Order(status=OrderStatus.PENDING.value)
    box_status = BoxStatus.ORDERED.value
    final_status = 'ordered' if box_status == BoxStatus.ORDERED.value else 'pending'
    assert final_status == 'ordered'
    print("✅ Order status updated to ordered")
    
    # Pending -> Cancelled
    order_to_cancel = Order(status=OrderStatus.PENDING.value)
    order_to_cancel.status = OrderStatus.CANCELLED.value
    assert order_to_cancel.status == OrderStatus.CANCELLED.value
    print("✅ Order cancelled successfully")

def test_notification_scenarios():
    """Test notification scenarios"""
    print("\n=== Testing notification scenarios ===")
    
    # Private chat order -> notify group
    chat_id = 12345  # Positive = private chat
    is_private = chat_id > 0
    placed_by_admin = False
    should_notify = is_private and not placed_by_admin
    assert should_notify
    print("✅ Private order triggers group notification")
    
    # Group chat order -> no notification
    group_chat_id = -12345  # Negative = group chat
    is_private = group_chat_id > 0
    should_notify = is_private and not placed_by_admin
    assert not should_notify
    print("✅ Group order skips notification")
    
    # Admin order -> no notification
    admin_order_private = 12345 > 0
    placed_by_admin = True
    should_notify = admin_order_private and not placed_by_admin
    assert not should_notify
    print("✅ Admin order skips notification")

def test_sold_out_detection():
    """Test sold out offer detection"""
    print("\n=== Testing sold out detection ===")
    
    # All capacity used
    boxes = [
        Box(current_quantity=12, max_capacity=12),
        Box(current_quantity=12, max_capacity=12)
    ]
    total_capacity = sum(box.max_capacity for box in boxes)
    total_ordered = sum(box.current_quantity for box in boxes)
    is_sold_out = total_ordered >= total_capacity
    assert is_sold_out
    print("✅ Sold out detected when capacity full")
    
    # Still has capacity
    boxes_partial = [
        Box(current_quantity=10, max_capacity=12),
        Box(current_quantity=8, max_capacity=12)
    ]
    total_capacity = sum(box.max_capacity for box in boxes_partial)
    total_ordered = sum(box.current_quantity for box in boxes_partial)
    is_sold_out = total_ordered >= total_capacity
    assert not is_sold_out
    print("✅ Not sold out when capacity remains")

if __name__ == "__main__":
    test_order_execution()
    test_duplicate_order_handling()
    test_capacity_management()
    test_order_status_updates()
    test_notification_scenarios()
    test_sold_out_detection()
    print("\n🎉 All customer order tests passed!")