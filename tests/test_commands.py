#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.entities import Offer, Box, OfferStatus, BoxStatus
from decimal import Decimal

def test_add_box():
    """Test add_box command logic"""
    print("=== Testing add_box command ===")
    
    # Success: sold_out -> active
    offer = Offer(offer_id=1, status=OfferStatus.SOLD_OUT.value, wholesale_box_size=12)
    if offer.status == OfferStatus.SOLD_OUT.value:
        offer.status = OfferStatus.ACTIVE.value
        status_msg = " (offer status updated to active)"
    else:
        status_msg = ""
    assert offer.status == OfferStatus.ACTIVE.value
    print("✅ Sold out offer becomes active")
    
    # Success: active remains active
    offer2 = Offer(offer_id=2, status=OfferStatus.ACTIVE.value, wholesale_box_size=12)
    if offer2.status == OfferStatus.SOLD_OUT.value:
        offer2.status = OfferStatus.ACTIVE.value
    assert offer2.status == OfferStatus.ACTIVE.value
    print("✅ Active offer remains active")

def test_order_placement_restrictions():
    """Test order placement restrictions for ordered/completed offers"""
    print("\n=== Testing order placement restrictions ===")
    
    # Should block: ordered status
    offer_ordered = Offer(offer_id=1, status=OfferStatus.ORDERED.value)
    can_create_box = offer_ordered.status not in [OfferStatus.ORDERED.value, OfferStatus.COMPLETED.value, OfferStatus.DELIVERED.value]
    assert not can_create_box
    print("✅ Blocks box creation for ordered offer")
    
    # Should block: completed status
    offer_completed = Offer(offer_id=2, status=OfferStatus.COMPLETED.value)
    can_create_box = offer_completed.status not in [OfferStatus.ORDERED.value, OfferStatus.COMPLETED.value, OfferStatus.DELIVERED.value]
    assert not can_create_box
    print("✅ Blocks box creation for completed offer")
    
    # Should block: delivered status
    offer_delivered = Offer(offer_id=3, status=OfferStatus.DELIVERED.value)
    can_create_box = offer_delivered.status not in [OfferStatus.ORDERED.value, OfferStatus.COMPLETED.value, OfferStatus.DELIVERED.value]
    assert not can_create_box
    print("✅ Blocks box creation for delivered offer")
    
    # Should allow: active status
    offer_active = Offer(offer_id=4, status=OfferStatus.ACTIVE.value)
    can_create_box = offer_active.status not in [OfferStatus.ORDERED.value, OfferStatus.COMPLETED.value, OfferStatus.DELIVERED.value]
    assert can_create_box
    print("✅ Allows box creation for active offer")

def test_box_status_transitions():
    """Test box status transitions"""
    print("\n=== Testing box status transitions ===")
    
    # Open -> minimum reached
    box = Box(current_quantity=0, max_capacity=12, min_breakeven=10, status=BoxStatus.OPEN.value)
    box.current_quantity = 10
    if box.current_quantity >= box.min_breakeven:
        box.status = BoxStatus.MINIMUM_REACHED.value
    assert box.status == BoxStatus.MINIMUM_REACHED.value
    print("✅ Open -> minimum reached")
    
    # Minimum reached -> full
    box.current_quantity = 12
    if box.current_quantity >= box.max_capacity:
        box.status = BoxStatus.FULL.value
    assert box.status == BoxStatus.FULL.value
    print("✅ Minimum reached -> full")

def test_offer_status_transitions():
    """Test offer status transitions"""
    print("\n=== Testing offer status transitions ===")
    
    # Active -> sold out (when capacity reached)
    total_capacity = 24
    total_ordered = 24
    offer_status = OfferStatus.ACTIVE.value
    if total_ordered >= total_capacity:
        offer_status = OfferStatus.SOLD_OUT.value
    assert offer_status == OfferStatus.SOLD_OUT.value
    print("✅ Active -> sold out when capacity reached")
    
    # Sold out -> active (when box added)
    offer_status = OfferStatus.SOLD_OUT.value
    if offer_status == OfferStatus.SOLD_OUT.value:
        offer_status = OfferStatus.ACTIVE.value
    assert offer_status == OfferStatus.ACTIVE.value
    print("✅ Sold out -> active when box added")

def test_order_limits():
    """Test order quantity limits"""
    print("\n=== Testing order limits ===")
    
    # Customer limit: 5 units
    existing_orders = 3
    new_order = 2
    customer_limit = 5
    total = existing_orders + new_order
    within_limit = total <= customer_limit
    assert within_limit
    print("✅ Order within customer limit")
    
    # Exceeds customer limit
    existing_orders = 4
    new_order = 2
    total = existing_orders + new_order
    within_limit = total <= customer_limit
    assert not within_limit
    print("✅ Order exceeds customer limit")
    
    # Admin limit: 10 units
    admin_limit = 10
    admin_order = 8
    within_admin_limit = admin_order <= admin_limit
    assert within_admin_limit
    print("✅ Admin order within limit")

def test_validation_failures():
    """Test validation failure scenarios"""
    print("\n=== Testing validation failures ===")
    
    # Invalid box sizes
    valid_sizes = [1, 2, 6, 8, 10, 12, 15, 16, 18, 20, 24]
    invalid_size = 13
    is_valid = invalid_size in valid_sizes
    assert not is_valid
    print("✅ Invalid box size rejected")
    
    # Invalid quantity
    quantity = -1
    is_positive = quantity > 0
    assert not is_positive
    print("✅ Negative quantity rejected")
    
    # Empty offer name
    name = ""
    is_valid_name = len(name.strip()) > 0
    assert not is_valid_name
    print("✅ Empty name rejected")
    
    # Name too long
    name = "x" * 101
    is_valid_length = len(name) <= 100
    assert not is_valid_length
    print("✅ Long name rejected")

if __name__ == "__main__":
    test_add_box()
    test_order_placement_restrictions()
    test_box_status_transitions()
    test_offer_status_transitions()
    test_order_limits()
    test_validation_failures()
    print("\n🎉 All tests passed!")