import boto3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from boto3.dynamodb.conditions import Key
from models.entities import Supplier, Offer, Customer, Box, Order, DiscountPeriod, DiscountStatus, BoxStatus
from services.user_cache import UserCache
from services.offer_cache import OfferCache
from repositories.supplier_repository import SupplierRepository
from repositories.offer_repository import OfferRepository
from repositories.system_repository import SystemRepository
from repositories.customer_repository import CustomerRepository
from repositories.box_repository import BoxRepository
from repositories.order_repository import OrderRepository
from repositories.order_history_repository import OrderHistoryRepository

class DynamoDBService:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.s3 = boto3.client('s3')
        self.table_prefix = os.environ.get('DYNAMODB_TABLE_PREFIX', 'ubbc-bot-test')
        self.s3_bucket = os.environ.get('S3_BUCKET_NAME', f'{self.table_prefix}-images')
        
        # Initialize repositories
        self.system_repo = SystemRepository()
        self.supplier_repo = SupplierRepository()
        self.offer_repo = OfferRepository(self.system_repo)
        self.customer_repo = CustomerRepository(self.system_repo)
        self.box_repo = BoxRepository()
        self.order_repo = OrderRepository()
        self.order_history_repo = OrderHistoryRepository()
        
        # Initialize tables (Legacy - to be removed)
        self.suppliers_table = self.dynamodb.Table(f'{self.table_prefix}-suppliers')
        self.offers_table = self.dynamodb.Table(f'{self.table_prefix}-offers')
        self.customers_table = self.dynamodb.Table(f'{self.table_prefix}-customers')
        self.boxes_table = self.dynamodb.Table(f'{self.table_prefix}-boxes')
        self.orders_table = self.dynamodb.Table(f'{self.table_prefix}-orders')
        self.discounts_table = self.dynamodb.Table(f'{self.table_prefix}-discounts')
        self.counters_table = self.dynamodb.Table(f'{self.table_prefix}-counters')
        self.notifications_table = self.dynamodb.Table(f'{self.table_prefix}-notifications')
        self.edit_contexts_table = self.dynamodb.Table(f'{self.table_prefix}-edit-contexts')
        self.order_history_table = self.dynamodb.Table(f'{self.table_prefix}-order-history')
        self.customer_credits_table = self.dynamodb.Table(f'{self.table_prefix}-customer-credits')
        self.credit_transactions_table = self.dynamodb.Table(f'{self.table_prefix}-credit-transactions')

    def _serialize_datetime(self, obj):
        """Convert datetime objects to ISO strings"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    def _prepare_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare item for DynamoDB storage"""
        prepared = {}
        for key, value in item.items():
            if isinstance(value, datetime):
                prepared[key] = value.isoformat()
            elif value is not None:
                prepared[key] = value
        return prepared

    def _get_next_offer_id(self) -> int:
        """Get next auto-incrementing offer ID"""
        return self.system_repo.get_next_id('offer_id')

    def get_next_guest_id(self) -> int:
        """Get next auto-incrementing guest ID"""
        return self.system_repo.get_next_id('guest_id')

    # Supplier operations
    def create_supplier(self, supplier: Supplier) -> bool:
        return self.supplier_repo.create_supplier(supplier)

    def get_supplier(self, supplier_id: str) -> Optional[Supplier]:
        return self.supplier_repo.get_supplier(supplier_id)

    def get_supplier_by_name(self, name: str) -> Optional[Supplier]:
        return self.supplier_repo.get_supplier_by_name(name)

    def update_supplier(self, supplier_id: str, updates: Dict[str, Any]) -> bool:
        return self.supplier_repo.update_supplier(supplier_id, updates)

    def list_suppliers(self) -> List[Supplier]:
        return self.supplier_repo.list_suppliers()

    # Offer operations
    def create_offer(self, offer: Offer) -> bool:
        return self.offer_repo.create_offer(offer)

    def get_offer(self, offer_id: int) -> Optional[Offer]:
        return self.offer_repo.get_offer(offer_id)

    def list_offers(self) -> List[Offer]:
        """Get all offers with caching"""
        return self.offer_repo.list_offers()
    
    def _list_offers_uncached(self) -> List[Offer]:
        """Internal method to get offers without caching"""
        return self.offer_repo._list_offers_uncached()
    
    def list_sold_out_offers_recent(self, days: int = 7) -> List[Offer]:
        """Get sold out offers from last N days"""
        return self.offer_repo.list_sold_out_offers_recent(days)

    def update_offer(self, offer_id: int, updates: Dict[str, Any]) -> bool:
        return self.offer_repo.update_offer(offer_id, updates)
    
    def append_offer_image(self, offer_id: int, image_url: str) -> bool:
        """Atomically append an image to offer's images list"""
        return self.offer_repo.append_offer_image(offer_id, image_url)

    def delete_box(self, box_id: str) -> bool:
        return self.box_repo.delete_box(box_id)

    # Customer operations
    def create_customer(self, customer: Customer) -> Optional[Customer]:
        """Create customer and invalidate cache"""
        return self.customer_repo.create_customer(customer)

    def get_customer_by_telegram_id(self, telegram_user_id: int) -> Optional[Customer]:
        """Get customer by telegram ID with caching"""
        return self.customer_repo.get_customer_by_telegram_id(telegram_user_id)
    
    def _get_customer_by_telegram_id_uncached(self, telegram_user_id: int) -> Optional[Customer]:
        """Internal method to get customer by telegram ID without caching"""
        return self.customer_repo._get_customer_by_telegram_id_uncached(telegram_user_id)

    # Box operations
    def create_box(self, box: Box) -> Optional[Box]:
        return self.box_repo.create_box(box)

    def get_boxes_by_offer(self, offer_id: int) -> List[Box]:
        return self.box_repo.get_boxes_by_offer(offer_id)

    def update_box(self, box_id: str, updates: Dict[str, Any]) -> bool:
        return self.box_repo.update_box(box_id, updates)

    # Order operations
    def create_order(self, order: Order, admin_id: int = 0) -> Optional[Order]:
        """Create order with automatic audit logging"""
        try:
            from services.audit_service import AuditService
            
            result = self.order_repo.create_order(order)
            if result:
                audit = AuditService(self)
                audit.log_order_created(order, admin_id)
            return result
        except Exception as e:
            print(f"Error creating order: {e}")
            return None

    def get_orders_by_customer(self, customer_id: str) -> List[Order]:
        return self.order_repo.get_orders_by_customer(customer_id)

    def get_orders_by_offer(self, offer_id: int) -> List[Order]:
        return self.order_repo.get_orders_by_offer(offer_id)
    
    def get_all_boxes(self) -> List[Box]:
        """Scan all boxes from DynamoDB with minimal fields for list_offers"""
        return self.box_repo.get_all_boxes()
    
    def get_all_orders(self, statuses: List[str] = None) -> List[Order]:
        """Scan all orders with minimal fields for list_offers"""
        return self.order_repo.get_all_orders(statuses)

    def get_orders_by_customer_and_offer(self, customer_id: str, offer_id: int) -> List[Order]:
        """Get orders for a specific customer and offer combination"""
        try:
            orders = self.get_orders_by_offer(offer_id)
            return [order for order in orders if order.customer_id == customer_id]
        except Exception as e:
            print(f"Error getting orders by customer and offer: {e}")
            return []

    def get_orders_by_customer_and_status(self, customer_id: str, status: str) -> List[Order]:
        """Get orders for a specific customer with specific status"""
        try:
            orders = self.get_orders_by_customer(customer_id)
            return [order for order in orders if order.status == status]
        except Exception as e:
            print(f"Error getting orders by customer and status: {e}")
            return []

    def get_orders_by_box(self, box_id: str) -> List[Order]:
        """Get all orders for a specific box"""
        return self.order_repo.get_orders_by_box(box_id)

    def get_active_discount(self) -> Optional[DiscountPeriod]:
        try:
            from datetime import datetime, UTC
            now = datetime.now(UTC)
            response = self.discounts_table.scan(
                FilterExpression='#status = :status AND start_time <= :now AND (attribute_not_exists(end_time) OR end_time > :now)',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': DiscountStatus.ACTIVE.value,
                    ':now': now.isoformat()
                }
            )
            items = response.get('Items', [])
            if items:
                return DiscountPeriod(**items[0])
            return None
        except Exception as e:
            print(f"Error getting active discount: {e}")
            return None

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.order_repo.get_order(order_id)

    def get_customer(self, customer_id: str) -> Optional[Customer]:
        return self.customer_repo.get_customer(customer_id)

    def get_box(self, box_id: str) -> Optional[Box]:
        return self.box_repo.get_box(box_id)

    def delete_order(self, order_id: str) -> bool:
        return self.order_repo.delete_order(order_id)

    def update_order(self, order_id: str, updates: Dict[str, Any], admin_id: int = 0, reason: str = "") -> bool:
        """Update order with automatic audit logging"""
        try:
            from services.audit_service import AuditService
            
            old_order = self.get_order(order_id)
            if not old_order:
                return False
            
            if not self.order_repo.update_order(order_id, updates):
                return False
            
            # Auto-log significant changes
            audit = AuditService(self)
            new_order = self.get_order(order_id)
            
            if 'total_price' in updates and old_order.total_price != new_order.total_price:
                audit.log_price_change(new_order, old_order.total_price, new_order.total_price, admin_id, reason)
            elif 'status' in updates and old_order.status != new_order.status:
                audit.log_status_change(new_order, old_order.status, new_order.status, admin_id, reason)
            
            return True
        except Exception as e:
            print(f"Error updating order: {e}")
            return False

    def get_customers_by_status(self, status: str) -> List[Customer]:
        """Get customers by status with caching"""
        return self.customer_repo.get_customers_by_status(status)
    
    def _get_customers_by_status_uncached(self, status: str) -> List[Customer]:
        """Internal method to get customers by status without caching"""
        return self.customer_repo._get_customers_by_by_status_uncached(status)

    def get_customer_by_username(self, username: str) -> Optional[Customer]:
        return self.customer_repo.get_customer_by_username(username)

    def get_customer_by_name(self, name: str) -> Optional[Customer]:
        """Search customer by name (first + last)"""
        return self.customer_repo.get_customer_by_name(name)

    def update_customer(self, customer_id: str, updates: Dict[str, Any]) -> bool:
        return self.customer_repo.update_customer(customer_id, updates)

    # Notification message operations
    def create_notification_message(self, notification) -> bool:
        try:
            item = self._prepare_item(notification.__dict__)
            self.notifications_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating notification message: {e}")
            return False

    def get_notification_messages_by_offer(self, offer_id: int):
        try:
            response = self.notifications_table.query(
                IndexName='offer-index',
                KeyConditionExpression=Key('offer_id').eq(offer_id)
            )
            from models.entities import NotificationMessage
            return [NotificationMessage(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting notification messages: {e}")
            return []

    def delete_notification_message(self, notification_id: str) -> bool:
        try:
            self.notifications_table.delete_item(Key={'notification_id': notification_id})
            return True
        except Exception as e:
            print(f"Error deleting notification message: {e}")
            return False
    def create_discount(self, discount: DiscountPeriod) -> bool:
        try:
            item = self._prepare_item(discount.__dict__)
            self.discounts_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating discount: {e}")
            return False
    
    def update_discount(self, discount_id: str, updates: Dict[str, Any]) -> bool:
        try:
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.discounts_table.update_item(
                Key={'discount_id': discount_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            print(f"Error updating discount: {e}")
            return False
    
    def create_edit_context(self, context) -> bool:
        """Create edit context"""
        try:
            item = self._prepare_item(context.__dict__)
            self.edit_contexts_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating edit context: {e}")
            return False
    
    def get_edit_context_by_chat_id(self, chat_id: int):
        """Get edit context by chat ID"""
        try:
            response = self.edit_contexts_table.scan(
                FilterExpression='chat_id = :chat_id',
                ExpressionAttributeValues={':chat_id': chat_id}
            )
            
            if response['Items']:
                item = response['Items'][0]
                from models.entities import EditContext
                from datetime import datetime
                return EditContext(
                    context_id=item['context_id'],
                    chat_id=item['chat_id'],
                    edit_type=item['edit_type'],
                    entity_id=item['entity_id'],
                    created_at=datetime.fromisoformat(item['created_at'])
                )
            return None
        except Exception as e:
            print(f"Error getting edit context: {e}")
            return None
    
    def delete_edit_context(self, context_id: str) -> bool:
        """Delete edit context"""
        try:
            self.edit_contexts_table.delete_item(
                Key={'context_id': context_id}
            )
            return True
        except Exception as e:
            print(f"Error deleting edit context: {e}")
            return False
    
    def get_subscribers(self) -> List[Customer]:
        """Get subscribers with caching"""
        return self.customer_repo.get_subscribers()
    
    def _get_subscribers_uncached(self) -> List[Customer]:
        """Internal method to get subscribers without caching"""
        return self.customer_repo._get_subscribers_uncached()

    def get_all_customers(self) -> List[Customer]:
        """Get all customers with caching"""
        return self.customer_repo.get_all_customers()

    def cleanup_old_edit_contexts(self) -> int:
        """Clean up edit contexts older than 1 hour"""
        try:
            from datetime import datetime, UTC, timedelta
            cutoff_time = datetime.now(UTC) - timedelta(hours=1)
            
            response = self.edit_contexts_table.scan(
                FilterExpression='created_at < :cutoff',
                ExpressionAttributeValues={':cutoff': cutoff_time.isoformat()}
            )
            
            deleted_count = 0
            for item in response.get('Items', []):
                if self.delete_edit_context(item['context_id']):
                    deleted_count += 1
            
            return deleted_count
        except Exception as e:
            print(f"Error cleaning up edit contexts: {e}")
            return 0
    
    def upload_image_to_s3(self, file_content: bytes, file_name: str, offer_id: int) -> Optional[str]:
        """Upload image to S3 and return URL"""
        try:
            key = f"offers/{offer_id}/{file_name}"
            self.s3.put_object(
                Bucket=self.s3_bucket,
                Key=key,
                Body=file_content,
                ContentType='image/jpeg'
            )
            return f"https://{self.s3_bucket}.s3.amazonaws.com/{key}"
        except Exception as e:
            print(f"Error uploading image to S3: {e}")
            return None
    
    def get_presigned_url(self, s3_url: str, expiration: int = 3600) -> Optional[str]:
        """Generate presigned URL for S3 object"""
        try:
            # Extract key from S3 URL
            if '.s3.amazonaws.com/' in s3_url:
                key = s3_url.split('.s3.amazonaws.com/')[1]
            else:
                return None
            
            presigned_url = self.s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.s3_bucket, 'Key': key},
                ExpiresIn=expiration
            )
            return presigned_url
        except Exception as e:
            print(f"Error generating presigned URL: {e}")
            return None
    
    def get_suppliers_with_boxes_by_status(self, box_status: str) -> List[Supplier]:
        """Get suppliers that have boxes with specified status"""
        try:
            # Get all boxes with specified status
            response = self.boxes_table.scan(
                FilterExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': box_status}
            )
            
            # Get unique offer IDs from boxes
            offer_ids = set()
            for item in response.get('Items', []):
                offer_ids.add(item['offer_id'])
            
            # Get supplier names from offers
            supplier_names = set()
            for offer_id in offer_ids:
                offer = self.get_offer(offer_id)
                if offer:
                    supplier_names.add(offer.supplier_name)
            
            # Get supplier objects
            suppliers = []
            for name in supplier_names:
                supplier = self.get_supplier_by_name(name)
                if supplier:
                    suppliers.append(supplier)
            
            return suppliers
        except Exception as e:
            print(f"Error getting suppliers with {box_status} boxes: {e}")
            return []

    def get_offers_by_supplier_and_box_status(self, supplier_name: str, box_status: str) -> List[Offer]:
        """Get offers for a supplier that have boxes with specified status"""
        try:
            # Get all boxes with specified status
            response = self.boxes_table.scan(
                FilterExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': box_status}
            )
            
            # Get offer IDs from boxes
            offer_ids = set()
            for item in response.get('Items', []):
                offer_ids.add(item['offer_id'])
            
            # Get offers for this supplier that have boxes with specified status
            offers = []
            for offer_id in offer_ids:
                offer = self.get_offer(offer_id)
                if offer and offer.supplier_name == supplier_name:
                    offers.append(offer)
            
            return offers
        except Exception as e:
            print(f"Error getting {box_status} offers by supplier: {e}")
            return []

    def get_suppliers_with_ordered_offers(self) -> List[Supplier]:
        """Get suppliers that have boxes with ORDERED status"""
        return self.get_suppliers_with_boxes_by_status('ordered')

    def get_ordered_offers_by_supplier(self, supplier_name: str) -> List[Offer]:
        """Get offers for a supplier that have boxes with ORDERED status"""
        return self.get_offers_by_supplier_and_box_status(supplier_name, 'ordered')

    def get_boxes_by_offer_with_orders(self, offer_id: int) -> List[Box]:
        """Get boxes for an offer that have orders"""
        try:
            boxes = self.get_boxes_by_offer(offer_id)
            boxes_with_orders = []
            
            for box in boxes:
                orders = self.get_orders_by_box(box.box_id)
                if orders:  # Only include boxes that have orders
                    boxes_with_orders.append(box)
            
            return boxes_with_orders
        except Exception as e:
            print(f"Error getting boxes with orders: {e}")
            return []

    def get_suppliers_with_ready_for_labeling_offers(self) -> List[Supplier]:
        """Get suppliers that have orders with READY_FOR_LABELING status"""
        return self.get_suppliers_with_orders_by_status('ready_for_labeling')

    def get_ready_for_labeling_offers_by_supplier(self, supplier_name: str) -> List[Offer]:
        """Get offers for a supplier that have orders with READY_FOR_LABELING status"""
        return self.get_offers_by_supplier_and_order_status(supplier_name, 'ready_for_labeling')

    def get_boxes_by_offer_with_ready_orders(self, offer_id: int) -> List[Box]:
        """Get boxes for an offer that have orders with READY_FOR_LABELING status"""
        return self.get_boxes_by_offer_with_order_status(offer_id, 'ready_for_labeling')

    def get_suppliers_with_orders_by_status(self, order_status: str) -> List[Supplier]:
        """Get suppliers that have orders with specified status"""
        try:
            # Get all orders with specified status
            response = self.orders_table.scan(
                FilterExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': order_status}
            )
            
            # Get unique offer IDs from orders
            offer_ids = set()
            for item in response.get('Items', []):
                offer_ids.add(item['offer_id'])
            
            # Get supplier names from offers
            supplier_names = set()
            for offer_id in offer_ids:
                offer = self.get_offer(offer_id)
                if offer:
                    supplier_names.add(offer.supplier_name)
            
            # Get supplier objects
            suppliers = []
            for name in supplier_names:
                supplier = self.get_supplier_by_name(name)
                if supplier:
                    suppliers.append(supplier)
            
            return suppliers
        except Exception as e:
            print(f"Error getting suppliers with {order_status} orders: {e}")
            return []

    def get_offers_by_supplier_and_order_status(self, supplier_name: str, order_status: str) -> List[Offer]:
        """Get offers for a supplier that have orders with specified status"""
        try:
            # Get all orders with specified status
            response = self.orders_table.scan(
                FilterExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': order_status}
            )
            
            # Get offer IDs from orders
            offer_ids = set()
            for item in response.get('Items', []):
                offer_ids.add(item['offer_id'])
            
            # Get offers for this supplier that have orders with specified status
            offers = []
            for offer_id in offer_ids:
                offer = self.get_offer(offer_id)
                if offer and offer.supplier_name == supplier_name:
                    offers.append(offer)
            
            return offers
        except Exception as e:
            print(f"Error getting {order_status} offers by supplier: {e}")
            return []

    def get_boxes_by_offer_with_order_status(self, offer_id: int, order_status: str) -> List[Box]:
        """Get boxes for an offer that have orders with specified status"""
        try:
            boxes = self.get_boxes_by_offer(offer_id)
            boxes_with_status_orders = []
            
            for box in boxes:
                orders = self.get_orders_by_box(box.box_id)
                status_orders = [o for o in orders if o.status == order_status]
                if status_orders:  # Only include boxes that have orders with specified status
                    boxes_with_status_orders.append(box)
            
            return boxes_with_status_orders
        except Exception as e:
            print(f"Error getting boxes with {order_status} orders: {e}")
            return []

    def delete_offer(self, offer_id: int) -> bool:
        try:
            self.offers_table.delete_item(Key={'offer_id': offer_id})
            
            # Invalidate cache
            OfferCache.invalidate_cache()
            
            return True
        except Exception as e:
            print(f"Error deleting offer: {e}")
            return False

    def delete_offer_images(self, offer_id: int) -> bool:
        """Delete all images for an offer from S3"""
        try:
            prefix = f"offers/{offer_id}/"
            response = self.s3.list_objects_v2(Bucket=self.s3_bucket, Prefix=prefix)
            
            if 'Contents' in response:
                objects = [{'Key': obj['Key']} for obj in response['Contents']]
                self.s3.delete_objects(
                    Bucket=self.s3_bucket,
                    Delete={'Objects': objects}
                )
            return True
        except Exception as e:
            print(f"Error deleting offer images: {e}")
            return False
    
    # Order History operations
    def create_order_history(self, history) -> bool:
        return self.order_history_repo.create_order_history(history)
    
    def get_order_history(self, order_id: str, limit: int = 50) -> List:
        return self.order_history_repo.get_order_history(order_id, limit)
    
    def get_customer_events(self, customer_id: str, event_type: Optional[str] = None, days: int = 30) -> List:
        return self.order_history_repo.get_customer_events(customer_id, event_type, days)
    
    def get_events_by_type(self, event_type: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List:
        return self.order_history_repo.get_events_by_type(event_type, start_date, end_date)
    
    def get_history_by_customer_name(self, customer_name: str, event_type: Optional[str] = None, limit: int = 50) -> List:
        return self.order_history_repo.get_history_by_customer_name(customer_name, event_type, limit)
    
    # Transaction methods for sensitive operations (audit enforced)
    def cancel_order_with_audit(self, order_id: str, admin_id: int, reason: str) -> bool:
        """Cancel order with mandatory audit logging"""
        try:
            from services.audit_service import AuditService
            
            order = self.get_order(order_id)
            if not order:
                return False
            
            # Log cancellation first
            audit = AuditService(self)
            audit.log_order_cancelled(order, admin_id, reason)
            
            # Then update order (will also log status change via update_order)
            return self.update_order(order_id, {'status': 'cancelled'}, admin_id, reason)
        except Exception as e:
            print(f"Error cancelling order with audit: {e}")
            return False
    
    def adjust_order_price_with_audit(self, order_id: str, new_price, admin_id: int, 
                                     reason: str, credit_transaction_id: Optional[str] = None) -> bool:
        """Adjust order price with mandatory audit logging and optional refund linkage"""
        try:
            from services.audit_service import AuditService
            from decimal import Decimal
            
            order = self.get_order(order_id)
            if not order:
                return False
            
            old_price = order.total_price
            new_price = Decimal(str(new_price))
            
            # Log price change with refund linkage
            audit = AuditService(self)
            audit.log_price_change(order, old_price, new_price, admin_id, reason, credit_transaction_id)
            
            # Update order (will also log via update_order, but price change already logged above)
            return self.update_order(order_id, {'total_price': new_price}, admin_id, reason)
        except Exception as e:
            print(f"Error adjusting order price with audit: {e}")
            return False
    
    def mark_order_paid_with_audit(self, order_id: str, admin_id: int) -> bool:
        """Mark order as paid with mandatory audit logging"""
        try:
            order = self.get_order(order_id)
            if not order:
                return False
            
            # Update order status (audit logging handled by update_order)
            return self.update_order(order_id, {'status': 'completed'}, admin_id, "Payment received")
        except Exception as e:
            print(f"Error marking order paid with audit: {e}")
            return False
    
    # Credit system operations
    def create_customer_credit(self, credit) -> bool:
        """Create customer credit record"""
        try:
            from models.entities import CustomerCredit
            item = self._prepare_item(credit.__dict__)
            self.customer_credits_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating customer credit: {e}")
            return False
    
    def get_customer_credit(self, customer_id: str):
        """Get customer credit by customer ID"""
        try:
            from models.entities import CustomerCredit
            response = self.customer_credits_table.get_item(Key={'customer_id': customer_id})
            if 'Item' in response:
                return CustomerCredit(**response['Item'])
            return None
        except Exception as e:
            print(f"Error getting customer credit: {e}")
            return None
    
    def update_customer_credit(self, customer_id: str, updates: Dict[str, Any]) -> bool:
        """Update customer credit balance"""
        try:
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = self._serialize_datetime(value)
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.customer_credits_table.update_item(
                Key={'customer_id': customer_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            print(f"Error updating customer credit: {e}")
            return False
    
    def create_credit_transaction(self, transaction) -> bool:
        """Create credit transaction record"""
        try:
            from models.entities import CreditTransaction
            item = self._prepare_item(transaction.__dict__)
            self.credit_transactions_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating credit transaction: {e}")
            return False
    
    def get_credit_transactions_by_customer(self, customer_id: str, limit: int = 50) -> List:
        """Get credit transactions for a customer"""
        try:
            from models.entities import CreditTransaction
            response = self.credit_transactions_table.query(
                IndexName='customer-index',
                KeyConditionExpression=Key('customer_id').eq(customer_id),
                Limit=limit,
                ScanIndexForward=False  # Most recent first
            )
            return [CreditTransaction(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting credit transactions: {e}")
            return []
    
    def get_customers_with_credit_balance(self, min_amount=None) -> List:
        """Get all customers with credit balance (optionally filtered by minimum amount)"""
        try:
            from models.entities import CustomerCredit
            from decimal import Decimal
            
            if min_amount:
                response = self.customer_credits_table.scan(
                    FilterExpression='current_balance >= :min_amount',
                    ExpressionAttributeValues={':min_amount': Decimal(str(min_amount))}
                )
            else:
                response = self.customer_credits_table.scan()
            
            return [CustomerCredit(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting customers with credit balance: {e}")
            return []