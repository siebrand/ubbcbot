#!/usr/bin/env python3
"""
Update unit price and total price for all orders of a specific offer.

Usage: python update_order_prices.py <environment> <offer_id> <new_unit_price>
Example: python update_order_prices.py test 123 12.50
"""

import sys
import os
import boto3
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from repositories.order_repository import OrderRepository

def update_order_prices(environment: str, offer_id: int, new_unit_price: Decimal):
    """Update prices for all orders of a specific offer"""
    
    # Set environment variable for table naming
    os.environ['DYNAMODB_TABLE_PREFIX'] = f'ubbc-bot-{environment}'
    
    # Initialize repository
    order_repo = OrderRepository()
    
    # Get all orders for the offer
    orders = order_repo.get_orders_by_offer(offer_id)
    
    if not orders:
        print(f"No orders found for offer {offer_id}")
        return
    
    print(f"Found {len(orders)} orders for offer {offer_id}")
    print(f"Updating unit_price to {new_unit_price}")
    print()
    
    updated_count = 0
    for order in orders:
        old_unit_price = order.unit_price
        old_total_price = order.total_price
        new_total_price = new_unit_price * order.quantity
        
        # Update order
        success = order_repo.update_order(order.order_id, {
            'unit_price': new_unit_price,
            'total_price': new_total_price
        })
        
        if success:
            updated_count += 1
            print(f"✓ Order {order.order_id}: {order.quantity}x €{old_unit_price} → €{new_unit_price} (total: €{old_total_price} → €{new_total_price})")
        else:
            print(f"✗ Failed to update order {order.order_id}")
    
    print()
    print(f"Updated {updated_count}/{len(orders)} orders")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python update_order_prices.py <environment> <offer_id> <new_unit_price>")
        print("Example: python update_order_prices.py test 123 12.50")
        sys.exit(1)
    
    environment = sys.argv[1]
    
    if environment not in ['test', 'prod']:
        print("Error: environment must be 'test' or 'prod'")
        sys.exit(1)
    
    try:
        offer_id = int(sys.argv[2])
        new_unit_price = Decimal(sys.argv[3])
    except ValueError as e:
        print(f"Error: Invalid offer_id or new_unit_price - {e}")
        sys.exit(1)
    
    if new_unit_price <= 0:
        print("Error: new_unit_price must be positive")
        sys.exit(1)
    
    print(f"Environment: {environment}")
    print(f"Offer ID: {offer_id}")
    print(f"New unit price: €{new_unit_price}")
    print()
    
    confirm = input("Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Aborted")
        sys.exit(0)
    
    update_order_prices(environment, offer_id, new_unit_price)
