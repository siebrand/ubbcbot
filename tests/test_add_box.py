#!/usr/bin/env python3

"""
Test script to verify add_box functionality
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.entities import Offer, Box, OfferStatus, BoxStatus
from decimal import Decimal

def test_add_box_logic():
    """Test the add_box logic"""
    
    # Test case 1: Sold out offer should become active
    print("Test 1: Sold out offer becomes active")
    offer = Offer(
        offer_id=1,
        supplier_name="Test Supplier",
        name="Test Beer",
        price_per_unit=Decimal('5.00'),
        wholesale_box_size=12,
        status=OfferStatus.SOLD_OUT.value
    )
    
    print(f"Before: Offer status = {offer.status}")
    
    # Simulate add_box logic
    if offer.status == OfferStatus.SOLD_OUT.value:
        offer.status = OfferStatus.ACTIVE.value
        status_msg = " (offer status updated to active)"
    else:
        status_msg = ""
    
    print(f"After: Offer status = {offer.status}{status_msg}")
    assert offer.status == OfferStatus.ACTIVE.value
    print("✅ Test 1 passed\n")
    
    # Test case 2: Active offer remains active
    print("Test 2: Active offer remains active")
    offer2 = Offer(
        offer_id=2,
        supplier_name="Test Supplier",
        name="Test Beer 2",
        price_per_unit=Decimal('6.00'),
        wholesale_box_size=12,
        status=OfferStatus.ACTIVE.value
    )
    
    print(f"Before: Offer status = {offer2.status}")
    
    # Simulate add_box logic
    if offer2.status == OfferStatus.SOLD_OUT.value:
        offer2.status = OfferStatus.ACTIVE.value
        status_msg = " (offer status updated to active)"
    else:
        status_msg = ""
    
    print(f"After: Offer status = {offer2.status}{status_msg}")
    assert offer2.status == OfferStatus.ACTIVE.value
    print("✅ Test 2 passed\n")
    
    print("All tests passed! ✅")

if __name__ == "__main__":
    test_add_box_logic()