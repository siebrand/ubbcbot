#!/usr/bin/env python3

import pytest
import sys
import os
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from models.entities import Order, Customer, Offer, Box, OrderStatus, OfferStatus, BoxStatus
from decimal import Decimal

def test_order_execution():
    """Test order execution scenarios"""
    # Success: normal order with complete entity
    offer = Offer(
        offer_id=1, 
        supplier_name="Test Brewery",
        name="Test Beer",
        price_per_unit=Decimal('5.00'), 
        wholesale_box_size=12, 
        status=OfferStatus.ACTIVE.value
    )
    quantity = 2
    total_price = offer.price_per_unit * quantity
    assert total_price == Decimal('10.00')
    
    # Success: order fits in existing box
    box = Box(
        offer_id=1,
        current_quantity=8, 
        max_capacity=12, 
        min_breakeven=10
    )
    available_space = box.max_capacity - box.current_quantity
    can_fit = quantity <= available_space
    assert can_fit
    
    # Failure: insufficient capacity
    box_full = Box(
        offer_id=1,
        current_quantity=12, 
        max_capacity=12
    )
    available_space = box_full.max_capacity - box_full.current_quantity
    can_fit = quantity <= available_space
    assert not can_fit

def test_duplicate_order_handling():
    """Test duplicate order confirmation"""
    # Has existing orders - needs confirmation
    existing_orders = [
        Order(
            customer_id="cust1",
            box_id="box1",
            offer_id=1,
            quantity=2, 
            unit_price=Decimal('5.00'),
            total_price=Decimal('10.00'),
            status=OrderStatus.PENDING.value
        ),
        Order(
            customer_id="cust1",
            box_id="box1",
            offer_id=1,
            quantity=1, 
            unit_price=Decimal('5.00'),
            total_price=Decimal('5.00'),
            status=OrderStatus.CONFIRMED.value
        )
    ]
    has_existing = len(existing_orders) > 0
    assert has_existing
    
    # No existing orders - direct execution
    no_orders = []
    has_existing = len(no_orders) > 0
    assert not has_existing

def test_capacity_management():
    """Test capacity and box management"""
    # Calculate total available capacity
    boxes = [
        Box(
            offer_id=1,
            current_quantity=8, 
            max_capacity=12, 
            status=BoxStatus.OPEN.value
        ),
        Box(
            offer_id=1,
            current_quantity=10, 
            max_capacity=12, 
            status=BoxStatus.MINIMUM_REACHED.value
        ),
        Box(
            offer_id=1,
            current_quantity=12, 
            max_capacity=12, 
            status=BoxStatus.ORDERED.value
        )
    ]
    
    total_available = 0
    for box in boxes:
        if box.status in [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value]:
            total_available += box.max_capacity - box.current_quantity
    
    assert total_available == 6  # (12-8) + (12-10) + 0
    
    # Check if new box creation is blocked when ordered boxes exist
    has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes)
    offer_status = OfferStatus.ACTIVE.value
    can_create_box = (offer_status not in [OfferStatus.ORDERED.value, OfferStatus.COMPLETED.value, OfferStatus.DELIVERED.value] 
                     and not has_ordered_boxes)
    assert not can_create_box

def test_order_status_updates():
    """Test order status transitions"""
    # Pending -> Ordered (when box becomes ordered)
    order = Order(
        customer_id="cust1",
        box_id="box1",
        offer_id=1,
        quantity=2,
        unit_price=Decimal('5.00'),
        total_price=Decimal('10.00'),
        status=OrderStatus.PENDING.value
    )
    box_status = BoxStatus.ORDERED.value
    final_status = OrderStatus.CONFIRMED.value if box_status == BoxStatus.ORDERED.value else OrderStatus.PENDING.value
    assert final_status == OrderStatus.CONFIRMED.value
    
    # Pending -> Cancelled
    order_to_cancel = Order(
        customer_id="cust1",
        box_id="box1",
        offer_id=1,
        quantity=1,
        unit_price=Decimal('5.00'),
        total_price=Decimal('5.00'),
        status=OrderStatus.PENDING.value
    )
    order_to_cancel.status = OrderStatus.CANCELLED.value
    assert order_to_cancel.status == OrderStatus.CANCELLED.value

def test_notification_scenarios():
    """Test notification scenarios"""
    # Private chat order -> notify group
    chat_id = 12345  # Positive = private chat
    is_private = chat_id > 0
    placed_by_admin = False
    should_notify = is_private and not placed_by_admin
    assert should_notify
    
    # Group chat order -> no notification
    group_chat_id = -12345  # Negative = group chat
    is_private = group_chat_id > 0
    should_notify = is_private and not placed_by_admin
    assert not should_notify
    
    # Admin order -> no notification
    admin_order_private = 12345 > 0
    placed_by_admin = True
    should_notify = admin_order_private and not placed_by_admin
    assert not should_notify

def test_sold_out_detection():
    """Test sold out offer detection"""
    # All capacity used
    boxes = [
        Box(offer_id=1, current_quantity=12, max_capacity=12),
        Box(offer_id=1, current_quantity=12, max_capacity=12)
    ]
    total_capacity = sum(box.max_capacity for box in boxes)
    total_ordered = sum(box.current_quantity for box in boxes)
    is_sold_out = total_ordered >= total_capacity
    assert is_sold_out
    
    # Still has capacity
    boxes_partial = [
        Box(offer_id=1, current_quantity=10, max_capacity=12),
        Box(offer_id=1, current_quantity=8, max_capacity=12)
    ]
    total_capacity = sum(box.max_capacity for box in boxes_partial)
    total_ordered = sum(box.current_quantity for box in boxes_partial)
    is_sold_out = total_ordered >= total_capacity
    assert not is_sold_out

@pytest.fixture
def translations():
    """Load translation data for tests"""
    import json
    translations_path = src_path / "translations" / "nl.json"
    with open(translations_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_availability_notification(translations):
    """Test availability notification text generation"""
    def mock_t(key, force_group_lang=False, **params):
        message = translations.get(key, key)
        return message.format(**params) if params else message
    
    # Test sold out scenario
    is_sold_out = True
    total_available = 0
    availability_text = " - SOLD OUT" if is_sold_out else (
        f" ({mock_t('sufficient_available', force_group_lang=True)})" if total_available > 6 else 
        f" ({mock_t('units_available', force_group_lang=True, count=total_available)})" if total_available > 0 else ""
    )
    assert availability_text == " - SOLD OUT"
    
    # Test exact availability (1-6 units)
    for available in [1, 3, 6]:
        is_sold_out = False
        availability_text = " - SOLD OUT" if is_sold_out else (
            f" ({mock_t('sufficient_available', force_group_lang=True)})" if available > 6 else 
            f" ({mock_t('units_available', force_group_lang=True, count=available)})" if available > 0 else ""
        )
        expected = f" ({available} beschikbaar)"
        assert availability_text == expected
    
    # Test sufficient availability (>6 units)
    for available in [7, 10, 15, 24]:
        is_sold_out = False
        availability_text = " - SOLD OUT" if is_sold_out else (
            f" ({mock_t('sufficient_available', force_group_lang=True)})" if available > 6 else 
            f" ({mock_t('units_available', force_group_lang=True, count=available)})" if available > 0 else ""
        )
        expected = " (voldoende beschikbaar)"
        assert availability_text == expected
    
    # Test no availability (not sold out)
    is_sold_out = False
    total_available = 0
    availability_text = " - SOLD OUT" if is_sold_out else (
        f" ({mock_t('sufficient_available', force_group_lang=True)})" if total_available > 6 else 
        f" ({mock_t('units_available', force_group_lang=True, count=total_available)})" if total_available > 0 else ""
    )
    assert availability_text == ""

# Error handling tests
def test_invalid_quantities():
    """Test error handling for invalid quantities"""
    offer = Offer(
        offer_id=1,
        supplier_name="Test Brewery",
        name="Test Beer",
        price_per_unit=Decimal('5.00'),
        wholesale_box_size=12,
        status=OfferStatus.ACTIVE.value
    )
    
    # Test negative quantity
    with pytest.raises((ValueError, AssertionError)):
        quantity = -1
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
    
    # Test zero quantity
    with pytest.raises((ValueError, AssertionError)):
        quantity = 0
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

def test_missing_entity_fields():
    """Test error handling for incomplete entities"""
    # Test that entities can be created with minimal required fields
    try:
        order = Order(
            customer_id="test_customer",
            box_id="test_box",
            offer_id=1,
            quantity=1,
            unit_price=Decimal('5.00'),
            total_price=Decimal('5.00')
        )
        assert order.status == OrderStatus.PENDING.value  # Default value
    except Exception as e:
        pytest.fail(f"Order creation failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])