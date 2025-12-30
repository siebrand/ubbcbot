from typing import List, Optional
from models.entities import Order, Box, OrderStatus, BoxStatus
from services.database import DynamoDBService

class WholesalerDeliveryService:
    def __init__(self, db_service: DynamoDBService):
        self.db = db_service
    
    def process_wholesaler_delivery(self, box_id: str, units_received: int, is_delayed: bool) -> bool:
        """
        Process wholesaler delivery and handle discrepancies
        
        Args:
            box_id: ID of the box being delivered
            units_received: Number of units actually received
            is_delayed: True if missing units will arrive later, False if cancelled
            
        Returns:
            bool: True if processing successful
        """
        try:
            # Get box and validate
            box = self.db.get_box(box_id)
            if not box:
                return False
            
            # Get all orders for this box
            orders = self._get_orders_by_box(box_id)
            if not orders:
                return False
            
            # Calculate expected vs received
            total_expected = sum(order.quantity for order in orders)
            
            if units_received == total_expected:
                # Full match - all units received
                self._process_full_delivery(orders, box_id)
            elif units_received < total_expected:
                # Partial delivery
                missing_units = total_expected - units_received
                if is_delayed:
                    self._process_partial_delayed(orders, units_received, missing_units, box_id)
                else:
                    self._process_partial_cancelled(orders, units_received, missing_units, box_id)
            
            return True
            
        except Exception as e:
            print(f"Error processing wholesaler delivery: {e}")
            return False
    
    def _get_orders_by_box(self, box_id: str) -> List[Order]:
        """Get all orders for a specific box"""
        return self.db.get_orders_by_box(box_id)
    
    def _process_full_delivery(self, orders: List[Order], box_id: str):
        """Process full delivery - all units received"""
        for order in orders:
            self.db.update_order(order.order_id, {
                'received_quantity': order.quantity,
                'status': OrderStatus.READY_FOR_LABELING.value
            })
        
        # Update box status to DELIVERED
        self.db.update_box(box_id, {'status': BoxStatus.DELIVERED.value})
    
    def _process_partial_delayed(self, orders: List[Order], units_received: int, missing_units: int, box_id: str):
        """Process partial delivery where missing units are delayed"""
        remaining_to_allocate = units_received
        
        for order in orders:
            if remaining_to_allocate <= 0:
                # No more units to allocate - mark as delayed
                self.db.update_order(order.order_id, {
                    'received_quantity': 0,
                    'status': OrderStatus.RECEIVED_PARTIAL_DELAYED.value
                })
                self.notify_customer_of_delay(order.order_id)
            elif remaining_to_allocate >= order.quantity:
                # Full order can be fulfilled
                self.db.update_order(order.order_id, {
                    'received_quantity': order.quantity,
                    'status': OrderStatus.READY_FOR_LABELING.value
                })
                remaining_to_allocate -= order.quantity
            else:
                # Partial fulfillment of this order
                self.db.update_order(order.order_id, {
                    'received_quantity': remaining_to_allocate,
                    'status': OrderStatus.RECEIVED_PARTIAL_DELAYED.value
                })
                self.notify_customer_of_delay(order.order_id)
                remaining_to_allocate = 0
        
        # Update box status to DELIVERED (partial delivery still means box is delivered)
        self.db.update_box(box_id, {'status': BoxStatus.DELIVERED.value})
    
    def _process_partial_cancelled(self, orders: List[Order], units_received: int, missing_units: int, box_id: str):
        """Process partial delivery where missing units are cancelled"""
        remaining_to_allocate = units_received
        
        for order in orders:
            if remaining_to_allocate <= 0:
                # No more units to allocate - cancel entire order
                self.db.update_order(order.order_id, {
                    'received_quantity': 0,
                    'status': OrderStatus.CANCELLED_UNAVAILABLE.value
                })
                self.notify_customer_of_cancellation(order.order_id)
            elif remaining_to_allocate >= order.quantity:
                # Full order can be fulfilled
                self.db.update_order(order.order_id, {
                    'received_quantity': order.quantity,
                    'status': OrderStatus.READY_FOR_LABELING.value
                })
                remaining_to_allocate -= order.quantity
            else:
                # Partial fulfillment - received units go to labeling, rest cancelled
                self.db.update_order(order.order_id, {
                    'received_quantity': remaining_to_allocate,
                    'status': OrderStatus.READY_FOR_LABELING.value
                })
                
                # Create new order record for cancelled portion
                cancelled_order = Order(
                    customer_id=order.customer_id,
                    box_id=order.box_id,
                    offer_id=order.offer_id,
                    quantity=order.quantity - remaining_to_allocate,
                    received_quantity=0,
                    unit_price=order.unit_price,
                    total_price=order.unit_price * (order.quantity - remaining_to_allocate),
                    status=OrderStatus.CANCELLED_UNAVAILABLE.value,
                    placed_by_admin=order.placed_by_admin
                )
                self.db.create_order(cancelled_order)
                self.notify_customer_of_cancellation(cancelled_order.order_id)
                remaining_to_allocate = 0
        
        # Update box status to DELIVERED (partial delivery still means box is delivered)
        self.db.update_box(box_id, {'status': BoxStatus.DELIVERED.value})
    
    def notify_customer_of_delay(self, order_id: str):
        """Stub method for notifying customer of delay"""
        print(f"STUB: Notifying customer of delay for order {order_id}")
    
    def notify_customer_of_cancellation(self, order_id: str):
        """Stub method for notifying customer of cancellation"""
        print(f"STUB: Notifying customer of cancellation for order {order_id}")
