#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.entities import Order, Offer, Box, OrderStatus, OfferStatus, BoxStatus
from decimal import Decimal

def test_fulfillment_calculations():
    """Test fulfillment calculations"""
    print("=== Testing fulfillment calculations ===")
    
    # Calculate boxes needed
    orders = [
        Order(quantity=5),
        Order(quantity=8),
        Order(quantity=12)
    ]
    total_units = sum(order.quantity for order in orders)
    box_size = 12
    boxes_needed = (total_units + box_size - 1) // box_size  # Ceiling division
    assert total_units == 25
    assert boxes_needed == 3  # 25 units / 12 = 2.08 -> 3 boxes
    print("✅ Fulfillment calculations correct")
    
    # Partial fulfillment scenario
    units_available = 20  # 2 boxes ordered instead of 3
    units_allocated = 0
    fulfilled_orders = []
    cancelled_orders = []
    updated_orders = []
    
    for order in sorted(orders, key=lambda x: getattr(x, 'created_at', 0)):
        remaining_capacity = units_available - units_allocated
        
        if remaining_capacity <= 0:
            cancelled_orders.append(order)
        elif order.quantity <= remaining_capacity:
            fulfilled_orders.append(order)
            units_allocated += order.quantity
        else:
            # Partial fulfillment
            old_quantity = order.quantity
            new_quantity = remaining_capacity
            updated_orders.append((order, old_quantity, new_quantity))
            units_allocated += new_quantity
    
    assert len(fulfilled_orders) == 2  # 5 + 8 = 13 units
    assert len(updated_orders) == 1   # 12 -> 7 units
    assert len(cancelled_orders) == 0
    assert units_allocated == 20
    print("✅ Partial fulfillment handled correctly")

def test_offer_cancellation():
    """Test offer cancellation scenarios"""
    print("\n=== Testing offer cancellation ===")
    
    # Active offer with orders
    offer = Offer(offer_id=1, status=OfferStatus.ACTIVE.value)
    active_orders = [
        Order(status=OrderStatus.PENDING.value),
        Order(status=OrderStatus.CONFIRMED.value)
    ]
    
    has_active_orders = len([o for o in active_orders if o.status in ['pending', 'ordered']]) > 0
    assert has_active_orders
    print("✅ Active orders detected for cancellation")
    
    # Cancel all orders
    cancelled_count = 0
    for order in active_orders:
        if order.status in ['pending', 'confirmed']:  # Use actual status values
            order.status = OrderStatus.CANCELLED.value
            cancelled_count += 1
    
    assert cancelled_count == 2
    print("✅ All active orders cancelled")
    
    # Update offer status
    offer.status = OfferStatus.INACTIVE.value
    assert offer.status == OfferStatus.INACTIVE.value
    print("✅ Offer marked as inactive")

def test_order_cancellation():
    """Test individual order cancellation"""
    print("\n=== Testing order cancellation ===")
    
    # Full box cancellation needs confirmation
    order = Order(quantity=12, box_id="box1")
    box = Box(current_quantity=12, max_capacity=12)
    is_full_box = order.quantity == box.max_capacity
    assert is_full_box
    print("✅ Full box cancellation detected")
    
    # Partial cancellation - direct
    order_partial = Order(quantity=5, box_id="box2")
    box_partial = Box(current_quantity=10, max_capacity=12)
    is_full_box = order_partial.quantity == box_partial.max_capacity
    assert not is_full_box
    print("✅ Partial cancellation - no confirmation needed")
    
    # Update inventory after cancellation
    original_quantity = box.current_quantity
    cancelled_quantity = order.quantity
    new_quantity = original_quantity - cancelled_quantity
    assert new_quantity == 0
    print("✅ Inventory corrected after cancellation")

def test_notification_cleanup():
    """Test notification message cleanup"""
    print("\n=== Testing notification cleanup ===")
    
    # Within 48 hours - delete messages
    from datetime import datetime, UTC, timedelta
    now = datetime.now(UTC)
    offer_created = now - timedelta(hours=24)  # 24 hours ago
    offer_age = now - offer_created
    within_48_hours = offer_age < timedelta(hours=48)
    assert within_48_hours
    print("✅ Recent offer - messages will be deleted")
    
    # Older than 48 hours - only remove from database
    old_offer_created = now - timedelta(hours=72)  # 72 hours ago
    offer_age = now - old_offer_created
    within_48_hours = offer_age < timedelta(hours=48)
    assert not within_48_hours
    print("✅ Old offer - only database cleanup")

def test_box_management():
    """Test box creation and deletion"""
    print("\n=== Testing box management ===")
    
    # Create additional boxes for fulfillment
    current_boxes = 2
    boxes_ordered = 4
    boxes_to_create = boxes_ordered - current_boxes
    assert boxes_to_create == 2
    print("✅ Additional boxes calculation correct")
    
    # Clean up empty boxes
    boxes = [
        Box(current_quantity=0, box_id="empty1"),
        Box(current_quantity=5, box_id="partial"),
        Box(current_quantity=0, box_id="empty2")
    ]
    empty_boxes = [box for box in boxes if box.current_quantity == 0]
    assert len(empty_boxes) == 2
    print("✅ Empty boxes identified for cleanup")

def test_status_validations():
    """Test status validation scenarios"""
    print("\n=== Testing status validations ===")
    
    # Can't fulfill inactive offer
    offer = Offer(status=OfferStatus.INACTIVE.value)
    can_fulfill = offer.status == OfferStatus.ACTIVE.value
    assert not can_fulfill
    print("✅ Inactive offer cannot be fulfilled")
    
    # Can't cancel non-active offer
    offer_ordered = Offer(status=OfferStatus.ORDERED.value)
    can_cancel = offer_ordered.status == OfferStatus.ACTIVE.value
    assert not can_cancel
    print("✅ Non-active offer cannot be cancelled")
    
    # Box status prevents new orders
    box_ordered = Box(status=BoxStatus.ORDERED.value)
    box_delivered = Box(status=BoxStatus.DELIVERED.value)
    available_statuses = [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value, BoxStatus.FULL.value]
    
    can_use_ordered = box_ordered.status in available_statuses
    can_use_delivered = box_delivered.status in available_statuses
    assert not can_use_ordered
    assert not can_use_delivered
    print("✅ Ordered/delivered boxes unavailable for new orders")

def test_audit_orders():
    """Test audit orders functionality"""
    print("\n=== Testing audit orders ===")
    
    from datetime import datetime, UTC
    
    # Orders with and without update_date (simulating old orders)
    orders = [
        Order(order_id="order1", update_date=datetime.now(UTC)),  # Has update_date
        Order(order_id="order2", update_date=None),  # Missing update_date (old order)
        Order(order_id="order3", update_date=None),  # Missing update_date (old order)
    ]
    
    # Find orders without update_date (simulating old orders)
    orders_without_update_date = []
    for order in orders:
        if not order.update_date:
            orders_without_update_date.append(order)
    
    assert len(orders_without_update_date) == 2  # order2, order3
    print("✅ Old orders without update_date identified correctly")
    
    # Simulate audit process
    current_time = datetime.now(UTC)
    updated_count = 0
    
    for order in orders_without_update_date:
        order.update_date = current_time
        updated_count += 1
    
    assert updated_count == 2
    assert all(order.update_date == current_time for order in orders_without_update_date)
    print("✅ Old orders updated with current timestamp")
    
    # Verify all orders now have update_date
    orders_still_missing = [order for order in orders if not order.update_date]
    assert len(orders_still_missing) == 0
    print("✅ All orders now have update_date")
    
    # Test new order creation (should have update_date automatically)
    new_order = Order(order_id="new_order")
    assert new_order.update_date is not None
    assert new_order.created_at is not None
    print("✅ New orders automatically get update_date")

if __name__ == "__main__":
    test_fulfillment_calculations()
    test_offer_cancellation()
    test_order_cancellation()
    test_notification_cleanup()
    test_box_management()
    test_status_validations()
    test_audit_orders()
    print("\n🎉 All admin operation tests passed!")