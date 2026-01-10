import boto3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from boto3.dynamodb.conditions import Key
from models.entities import Supplier, Offer, Customer, Box, Order, DiscountPeriod, DiscountStatus, BoxStatus
from services.user_cache import UserCache
from services.offer_cache import OfferCache

class DynamoDBService:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.s3 = boto3.client('s3')
        self.table_prefix = os.environ.get('DYNAMODB_TABLE_PREFIX', 'ubbc-bot-test')
        self.s3_bucket = os.environ.get('S3_BUCKET_NAME', f'{self.table_prefix}-images')
        
        # Initialize tables
        self.suppliers_table = self.dynamodb.Table(f'{self.table_prefix}-suppliers')
        self.offers_table = self.dynamodb.Table(f'{self.table_prefix}-offers')
        self.customers_table = self.dynamodb.Table(f'{self.table_prefix}-customers')
        self.boxes_table = self.dynamodb.Table(f'{self.table_prefix}-boxes')
        self.orders_table = self.dynamodb.Table(f'{self.table_prefix}-orders')
        self.discounts_table = self.dynamodb.Table(f'{self.table_prefix}-discounts')
        self.counters_table = self.dynamodb.Table(f'{self.table_prefix}-counters')
        self.notifications_table = self.dynamodb.Table(f'{self.table_prefix}-notifications')
        self.edit_contexts_table = self.dynamodb.Table(f'{self.table_prefix}-edit-contexts')

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
        try:
            response = self.counters_table.update_item(
                Key={'counter_name': 'offer_id'},
                UpdateExpression='ADD #val :inc',
                ExpressionAttributeNames={'#val': 'value'},
                ExpressionAttributeValues={':inc': 1},
                ReturnValues='UPDATED_NEW'
            )
            return int(response['Attributes']['value'])
        except Exception as e:
            print(f"Error getting next offer ID: {e}")
            # Initialize counter if it doesn't exist
            try:
                self.counters_table.put_item(
                    Item={'counter_name': 'offer_id', 'value': 1},
                    ConditionExpression='attribute_not_exists(counter_name)'
                )
                return 1
            except Exception:
                return 1

    def get_next_guest_id(self) -> int:
        """Get next auto-incrementing guest ID"""
        try:
            response = self.counters_table.update_item(
                Key={'counter_name': 'guest_id'},
                UpdateExpression='ADD #val :inc',
                ExpressionAttributeNames={'#val': 'value'},
                ExpressionAttributeValues={':inc': 1},
                ReturnValues='UPDATED_NEW'
            )
            return int(response['Attributes']['value'])
        except Exception as e:
            print(f"Error getting next guest ID: {e}")
            # Initialize counter if it doesn't exist
            try:
                self.counters_table.put_item(
                    Item={'counter_name': 'guest_id', 'value': 1},
                    ConditionExpression='attribute_not_exists(counter_name)'
                )
                return 1
            except Exception:
                return 1

    # Supplier operations
    def create_supplier(self, supplier: Supplier) -> bool:
        try:
            # Check for duplicate name (case-insensitive)
            existing = self.get_supplier_by_name(supplier.name)
            if existing:
                return False
            
            item = self._prepare_item(supplier.__dict__)
            self.suppliers_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating supplier: {e}")
            return False

    def get_supplier(self, supplier_id: str) -> Optional[Supplier]:
        try:
            response = self.suppliers_table.get_item(Key={'supplier_id': supplier_id})
            if 'Item' in response:
                return Supplier(**response['Item'])
            return None
        except Exception as e:
            print(f"Error getting supplier: {e}")
            return None

    def get_supplier_by_name(self, name: str) -> Optional[Supplier]:
        try:
            response = self.suppliers_table.scan(
                FilterExpression='#name = :name',
                ExpressionAttributeNames={'#name': 'name'},
                ExpressionAttributeValues={':name': name.strip()}
            )
            items = response.get('Items', [])
            if items:
                return Supplier(**items[0])
            return None
        except Exception as e:
            print(f"Error getting supplier by name: {e}")
            return None

    def update_supplier(self, supplier_id: str, updates: Dict[str, Any]) -> bool:
        try:
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.suppliers_table.update_item(
                Key={'supplier_id': supplier_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            print(f"Error updating supplier: {e}")
            return False

    def list_suppliers(self) -> List[Supplier]:
        try:
            response = self.suppliers_table.scan()
            return [Supplier(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error listing suppliers: {e}")
            return []

    # Offer operations
    def create_offer(self, offer: Offer) -> bool:
        try:
            # Get next offer ID if not set
            if offer.offer_id == 0:
                offer.offer_id = self._get_next_offer_id()
            
            item = self._prepare_item(offer.__dict__)
            self.offers_table.put_item(Item=item)
            
            # Invalidate cache
            OfferCache.invalidate_cache()
            
            return True
        except Exception as e:
            print(f"Error creating offer: {e}")
            return False

    def get_offer(self, offer_id: int) -> Optional[Offer]:
        try:
            # Ensure offer_id is an integer (handle float inputs)
            offer_id = int(offer_id)
            response = self.offers_table.get_item(Key={'offer_id': offer_id})
            if 'Item' in response:
                item = response['Item']
                # Convert Decimal fields to appropriate types
                if 'wholesale_box_size' in item:
                    item['wholesale_box_size'] = int(item['wholesale_box_size'])
                # Remove deprecated fields for backward compatibility
                item.pop('min_quantity_breakeven', None)
                return Offer(**item)
            return None
        except Exception as e:
            print(f"Error getting offer: {e}")
            return None

    def list_offers(self) -> List[Offer]:
        """Get all offers with caching"""
        return OfferCache.get_offers(self)
    
    def _list_offers_uncached(self) -> List[Offer]:
        """Internal method to get offers without caching"""
        try:
            response = self.offers_table.scan()
            offers = []
            for item in response.get('Items', []):
                # Convert Decimal fields to appropriate types
                if 'wholesale_box_size' in item:
                    item['wholesale_box_size'] = int(item['wholesale_box_size'])
                # Remove deprecated fields for backward compatibility
                item.pop('min_quantity_breakeven', None)
                offers.append(Offer(**item))
            return offers
        except Exception as e:
            print(f"Error listing offers: {e}")
            return []
    
    def list_sold_out_offers_recent(self, days: int = 7) -> List[Offer]:
        """Get sold out offers from last N days"""
        try:
            from datetime import datetime, timedelta, UTC
            cutoff_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()
            
            response = self.offers_table.scan(
                FilterExpression='#status = :status AND created_at >= :cutoff',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'sold_out',
                    ':cutoff': cutoff_date
                }
            )
            return [Offer(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error listing recent sold out offers: {e}")
            return []

    def update_offer(self, offer_id: int, updates: Dict[str, Any]) -> bool:
        try:
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.offers_table.update_item(
                Key={'offer_id': offer_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            
            # Invalidate cache
            OfferCache.invalidate_cache()
            
            return True
        except Exception as e:
            print(f"Error updating offer: {e}")
            return False

    def delete_box(self, box_id: str) -> bool:
        try:
            self.boxes_table.delete_item(Key={'box_id': box_id})
            return True
        except Exception as e:
            print(f"Error deleting box: {e}")
            return False

    # Customer operations
    def create_customer(self, customer: Customer) -> Optional[Customer]:
        """Create customer and invalidate cache"""
        try:
            item = self._prepare_item(customer.__dict__)
            self.customers_table.put_item(Item=item)
            
            # Invalidate cache for the customer's status
            UserCache.invalidate_status_cache(customer.authorization_status)

            return customer
        except Exception as e:
            print(f"Error creating customer: {e}")
            return None

    def get_customer_by_telegram_id(self, telegram_user_id: int) -> Optional[Customer]:
        """Get customer by telegram ID with caching"""
        return UserCache.get_customer_by_telegram_id(telegram_user_id, self)
    
    def _get_customer_by_telegram_id_uncached(self, telegram_user_id: int) -> Optional[Customer]:
        """Internal method to get customer by telegram ID without caching"""
        try:
            response = self.customers_table.query(
                IndexName='telegram-user-index',
                KeyConditionExpression=Key('telegram_user_id').eq(telegram_user_id)
            )
            items = response.get('Items', [])
            if items:
                item = items[0]
                # Handle missing fields for backward compatibility
                if 'is_guest' not in item:
                    item['is_guest'] = False
                if 'contact_info' not in item:
                    item['contact_info'] = None
                return Customer(**item)
            return None
        except Exception as e:
            print(f"Error getting customer by telegram ID: {e}")
            return None

    # Box operations
    def create_box(self, box: Box) -> Optional[Box]:
        try:
            item = self._prepare_item(box.__dict__)
            self.boxes_table.put_item(Item=item)
            return box
        except Exception as e:
            print(f"Error creating box: {e}")
            return None

    def get_boxes_by_offer(self, offer_id: int) -> List[Box]:
        try:
            response = self.boxes_table.query(
                IndexName='offer-index',
                KeyConditionExpression=Key('offer_id').eq(offer_id)
            )
            boxes = []
            for item in response.get('Items', []):
                # Convert Decimal fields to appropriate types
                if 'current_quantity' in item:
                    item['current_quantity'] = int(item['current_quantity'])
                if 'max_capacity' in item:
                    item['max_capacity'] = int(item['max_capacity'])
                # Remove deprecated fields for backward compatibility
                item.pop('min_breakeven', None)
                # Handle deprecated status values
                if item.get('status') == 'minimum_reached':
                    item['status'] = BoxStatus.OPEN.value
                boxes.append(Box(**item))
            return boxes
        except Exception as e:
            print(f"Error getting boxes by offer: {e}")
            return []

    def update_box(self, box_id: str, updates: Dict[str, Any]) -> bool:
        try:
            update_expression = "SET "
            expression_values = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
            
            update_expression = update_expression.rstrip(", ")
            
            # Add expression attribute names for reserved keywords
            expression_names = {}
            for key in updates.keys():
                expression_names[f"#{key}"] = key
            
            self.boxes_table.update_item(
                Key={'box_id': box_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            print(f"Error updating box: {e}")
            return False

    # Order operations
    def create_order(self, order: Order) -> Optional[Order]:
        try:
            item = self._prepare_item(order.__dict__)
            self.orders_table.put_item(Item=item)
            return order
        except Exception as e:
            print(f"Error creating order: {e}")
            return None

    def get_orders_by_customer(self, customer_id: str) -> List[Order]:
        try:
            response = self.orders_table.query(
                IndexName='customer-index',
                KeyConditionExpression=Key('customer_id').eq(customer_id)
            )
            return [Order(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting orders by customer: {e}")
            return []

    def get_orders_by_offer(self, offer_id: int) -> List[Order]:
        try:
            response = self.orders_table.query(
                IndexName='offer-index',
                KeyConditionExpression=Key('offer_id').eq(offer_id)
            )
            return [Order(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting orders by offer: {e}")
            return []
    
    def get_all_boxes(self) -> List[Box]:
        """Scan all boxes from DynamoDB with minimal fields for list_offers"""
        try:
            response = self.boxes_table.scan(
                ProjectionExpression='box_id, offer_id, max_capacity, #status',
                ExpressionAttributeNames={'#status': 'status'}
            )
            boxes = []
            for item in response.get('Items', []):
                item['max_capacity'] = int(item['max_capacity'])
                if item.get('status') == 'minimum_reached':
                    item['status'] = BoxStatus.OPEN.value
                # Add default values for required Box fields not fetched
                item.setdefault('current_quantity', 0)
                boxes.append(Box(**item))
            return boxes
        except Exception as e:
            print(f"Error getting all boxes: {e}")
            return []
    
    def get_all_orders(self, statuses: List[str] = None) -> List[Order]:
        """Scan all orders with minimal fields for list_offers"""
        try:
            if statuses:
                filter_expr = ' OR '.join([f'#status = :status{i}' for i in range(len(statuses))])
                expr_values = {f':status{i}': status for i, status in enumerate(statuses)}
                response = self.orders_table.scan(
                    ProjectionExpression='order_id, offer_id, quantity, #status',
                    FilterExpression=filter_expr,
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues=expr_values
                )
            else:
                response = self.orders_table.scan(
                    ProjectionExpression='order_id, offer_id, quantity, #status',
                    ExpressionAttributeNames={'#status': 'status'}
                )
            # Add default values for required Order fields not fetched
            orders = []
            for item in response.get('Items', []):
                item.setdefault('customer_id', '')
                item.setdefault('box_id', '')
                item.setdefault('unit_price', 0)
                item.setdefault('total_price', 0)
                orders.append(Order(**item))
            return orders
        except Exception as e:
            print(f"Error getting all orders: {e}")
            return []

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
        try:
            response = self.orders_table.scan(
                FilterExpression='box_id = :box_id',
                ExpressionAttributeValues={':box_id': box_id}
            )
            return [Order(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting orders by box: {e}")
            return []

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
        try:
            response = self.orders_table.get_item(Key={'order_id': order_id})
            if 'Item' in response:
                return Order(**response['Item'])
            return None
        except Exception as e:
            print(f"Error getting order: {e}")
            return None

    def get_customer(self, customer_id: str) -> Optional[Customer]:
        try:
            response = self.customers_table.get_item(Key={'customer_id': customer_id})
            if 'Item' in response:
                item = response['Item']
                # Handle missing fields for backward compatibility
                if 'is_guest' not in item:
                    item['is_guest'] = False
                if 'contact_info' not in item:
                    item['contact_info'] = None
                return Customer(**item)
            return None
        except Exception as e:
            print(f"Error getting customer: {e}")
            return None

    def get_box(self, box_id: str) -> Optional[Box]:
        try:
            response = self.boxes_table.get_item(Key={'box_id': box_id})
            if 'Item' in response:
                item = response['Item']
                # Convert Decimal fields to appropriate types
                if 'current_quantity' in item:
                    item['current_quantity'] = int(item['current_quantity'])
                if 'max_capacity' in item:
                    item['max_capacity'] = int(item['max_capacity'])
                # Remove deprecated fields for backward compatibility
                item.pop('min_breakeven', None)
                # Handle deprecated status values
                if item.get('status') == 'minimum_reached':
                    item['status'] = BoxStatus.OPEN.value
                return Box(**item)
            return None
        except Exception as e:
            print(f"Error getting box: {e}")
            return None

    def delete_order(self, order_id: str) -> bool:
        try:
            self.orders_table.delete_item(Key={'order_id': order_id})
            return True
        except Exception as e:
            print(f"Error deleting order: {e}")
            return False

    def update_order(self, order_id: str, updates: Dict[str, Any]) -> bool:
        try:
            from datetime import datetime, UTC
            
            # Always add update_date to any order update
            updates = updates.copy()  # Don't modify the original dict
            updates['update_date'] = datetime.now(UTC).isoformat()
            
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.orders_table.update_item(
                Key={'order_id': order_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            print(f"Error updating order: {e}")
            return False

    def get_customers_by_status(self, status: str) -> List[Customer]:
        """Get customers by status with caching"""
        return UserCache.get_customers_by_status(status, self)
    
    def _get_customers_by_status_uncached(self, status: str) -> List[Customer]:
        """Internal method to get customers by status without caching"""
        try:
            response = self.customers_table.scan(
                FilterExpression='authorization_status = :status',
                ExpressionAttributeValues={':status': status}
            )
            customers = []
            for item in response.get('Items', []):
                # Handle missing fields for backward compatibility
                if 'is_guest' not in item:
                    item['is_guest'] = False
                if 'contact_info' not in item:
                    item['contact_info'] = None
                customers.append(Customer(**item))
            return customers
        except Exception as e:
            print(f"Error getting customers by status: {e}")
            return []

    def get_customer_by_username(self, username: str) -> Optional[Customer]:
        try:
            response = self.customers_table.scan(
                FilterExpression='username = :username',
                ExpressionAttributeValues={':username': username}
            )
            items = response.get('Items', [])
            if items:
                return Customer(**items[0])
            return None
        except Exception as e:
            print(f"Error getting customer by username: {e}")
            return None

    def get_customer_by_name(self, name: str) -> Optional[Customer]:
        try:
            response = self.customers_table.scan(
                FilterExpression='contains(first_name, :name) OR contains(last_name, :name)',
                ExpressionAttributeValues={':name': name}
            )
            items = response.get('Items', [])
            if items:
                return Customer(**items[0])
            return None
        except Exception as e:
            print(f"Error getting customer by name: {e}")
            return None

    def update_customer(self, customer_id: str, updates: Dict[str, Any]) -> bool:
        """Update customer and invalidate cache"""
        try:
            # Get current customer to determine status changes
            current_customer = self.get_customer(customer_id)
            
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.customers_table.update_item(
                Key={'customer_id': customer_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            
            # Invalidate relevant caches
            if current_customer:
                # Invalidate telegram_id cache
                UserCache.invalidate_customer_cache(current_customer.telegram_user_id)
                
                # If authorization status changed, invalidate both old and new status caches
                if 'authorization_status' in updates:
                    UserCache.invalidate_status_cache(current_customer.authorization_status)
                    UserCache.invalidate_status_cache(updates['authorization_status'])
                else:
                    # Otherwise just invalidate current status cache
                    UserCache.invalidate_status_cache(current_customer.authorization_status)
                
                # If subscription status changed, invalidate subscriber cache
                if 'subscribed_to_offers' in updates:
                    UserCache.invalidate_subscriber_cache()
            else:
                # If we can't determine current status, invalidate all caches
                UserCache.invalidate_cache()
            
            return True
        except Exception as e:
            print(f"Error updating customer: {e}")
            return False

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
        return UserCache.get_subscribers(self)
    
    def _get_subscribers_uncached(self) -> List[Customer]:
        """Internal method to get subscribers without caching"""
        try:
            response = self.customers_table.scan(
                FilterExpression='subscribed_to_offers = :subscribed',
                ExpressionAttributeValues={':subscribed': True}
            )
            customers = []
            for item in response.get('Items', []):
                # Handle missing fields for backward compatibility
                if 'is_guest' not in item:
                    item['is_guest'] = False
                if 'contact_info' not in item:
                    item['contact_info'] = None
                customers.append(Customer(**item))
            return customers
        except Exception as e:
            print(f"Error getting subscribers: {e}")
            return []

    def get_all_customers(self) -> List[Customer]:
        """Get all customers with caching"""
        return UserCache.get_all_customers(self)

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