import logging
from typing import Optional, List
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from models.entities import OrderHistory

logger = logging.getLogger()

class AuditService:
    """Service for logging order changes to audit trail"""
    
    def __init__(self, db):
        self.db = db
    
    def _get_customer_name(self, customer_id: str) -> str:
        """Get customer name for denormalization"""
        customer = self.db.get_customer(customer_id)
        if customer:
            parts = []
            if customer.first_name:
                parts.append(customer.first_name)
            if customer.last_name:
                parts.append(customer.last_name)
            return " ".join(parts) if parts else customer.username or "Unknown"
        return "Unknown"
    
    def _get_offer_name(self, offer_id: int) -> str:
        """Get offer name for denormalization"""
        offer = self.db.get_offer(offer_id)
        return offer.name if offer else "Unknown"
    
    def log_order_created(self, order, admin_id: int = 0):
        """Log order creation"""
        history = OrderHistory(
            order_id=order.order_id,
            customer_id=order.customer_id,
            customer_name=self._get_customer_name(order.customer_id),
            offer_name=self._get_offer_name(order.offer_id),
            event_type="ORDER_CREATED",
            changed_by=admin_id,
            field_name="order",
            old_value="",
            new_value=f"quantity={order.quantity}, total={order.total_price}",
            reason="Order placed"
        )
        self.db.create_order_history(history)
        logger.info(f"Audit: Order created {order.order_id}")
    
    def log_order_cancelled(self, order, admin_id: int, reason: str = ""):
        """Log order cancellation"""
        history = OrderHistory(
            order_id=order.order_id,
            customer_id=order.customer_id,
            customer_name=self._get_customer_name(order.customer_id),
            offer_name=self._get_offer_name(order.offer_id),
            event_type="ORDER_CANCELLED",
            changed_by=admin_id,
            field_name="status",
            old_value=order.status,
            new_value="cancelled",
            reason=reason or "Order cancelled by admin"
        )
        self.db.create_order_history(history)
        logger.info(f"Audit: Order cancelled {order.order_id}")
    
    def log_price_change(self, order, old_price: Decimal, new_price: Decimal, 
                        admin_id: int, reason: str = "", credit_transaction_id: Optional[str] = None):
        """Log price change (may trigger refund)"""
        history = OrderHistory(
            order_id=order.order_id,
            customer_id=order.customer_id,
            customer_name=self._get_customer_name(order.customer_id),
            offer_name=self._get_offer_name(order.offer_id),
            event_type="PRICE_CHANGED",
            changed_by=admin_id,
            field_name="total_price",
            old_value=str(old_price),
            new_value=str(new_price),
            reason=reason or "Price adjusted",
            credit_transaction_id=credit_transaction_id,
            triggers_refund=(credit_transaction_id is not None)
        )
        self.db.create_order_history(history)
        logger.info(f"Audit: Price changed {order.order_id}: {old_price} -> {new_price}")
    
    def log_payment_received(self, order, admin_id: int = 0):
        """Log payment received (status change to completed)"""
        history = OrderHistory(
            order_id=order.order_id,
            customer_id=order.customer_id,
            customer_name=self._get_customer_name(order.customer_id),
            offer_name=self._get_offer_name(order.offer_id),
            event_type="PAYMENT_RECEIVED",
            changed_by=admin_id,
            field_name="status",
            old_value="awaiting_payment",
            new_value="completed",
            reason="Payment received"
        )
        self.db.create_order_history(history)
        logger.info(f"Audit: Payment received {order.order_id}")
    
    def log_status_change(self, order, old_status: str, new_status: str, 
                         admin_id: int = 0, reason: str = ""):
        """Log generic status change"""
        # Determine event type
        if new_status == "completed" and old_status == "awaiting_payment":
            event_type = "PAYMENT_RECEIVED"
        elif new_status == "cancelled":
            event_type = "ORDER_CANCELLED"
        else:
            event_type = "STATUS_CHANGED"
        
        history = OrderHistory(
            order_id=order.order_id,
            customer_id=order.customer_id,
            customer_name=self._get_customer_name(order.customer_id),
            offer_name=self._get_offer_name(order.offer_id),
            event_type=event_type,
            changed_by=admin_id,
            field_name="status",
            old_value=old_status,
            new_value=new_status,
            reason=reason or f"Status changed to {new_status}"
        )
        self.db.create_order_history(history)
        logger.info(f"Audit: Status changed {order.order_id}: {old_status} -> {new_status}")
    
    def get_order_history(self, order_id: str, limit: int = 50) -> List[OrderHistory]:
        """Get complete history for an order"""
        return self.db.get_order_history(order_id, limit)
    
    def get_customer_events(self, customer_id: str, event_type: Optional[str] = None, 
                           days: int = 30) -> List[OrderHistory]:
        """Get events for a customer"""
        return self.db.get_customer_events(customer_id, event_type, days)
    
    def get_events_by_type(self, event_type: str, start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None) -> List[OrderHistory]:
        """Get all events of a specific type in date range"""
        return self.db.get_events_by_type(event_type, start_date, end_date)
