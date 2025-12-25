import boto3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from boto3.dynamodb.conditions import Key
from models.entities import Supplier, Offer, Customer, Box, Order, DiscountPeriod, DiscountStatus

class DynamoDBService:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.table_prefix = os.environ.get('DYNAMODB_TABLE_PREFIX', 'ubbc-bot-test')
        
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
            return True
        except Exception as e:
            print(f"Error creating offer: {e}")
            return False

    def get_offer(self, offer_id: int) -> Optional[Offer]:
        try:
            response = self.offers_table.get_item(Key={'offer_id': offer_id})
            if 'Item' in response:
                return Offer(**response['Item'])
            return None
        except Exception as e:
            print(f"Error getting offer: {e}")
            return None

    def list_offers(self) -> List[Offer]:
        try:
            response = self.offers_table.scan()
            return [Offer(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error listing offers: {e}")
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
    def create_customer(self, customer: Customer) -> bool:
        try:
            item = self._prepare_item(customer.__dict__)
            self.customers_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating customer: {e}")
            return False

    def get_customer_by_telegram_id(self, telegram_user_id: int) -> Optional[Customer]:
        try:
            response = self.customers_table.query(
                IndexName='telegram-user-index',
                KeyConditionExpression=Key('telegram_user_id').eq(telegram_user_id)
            )
            items = response.get('Items', [])
            if items:
                return Customer(**items[0])
            return None
        except Exception as e:
            print(f"Error getting customer by telegram ID: {e}")
            return None

    # Box operations
    def create_box(self, box: Box) -> bool:
        try:
            item = self._prepare_item(box.__dict__)
            self.boxes_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating box: {e}")
            return False

    def get_boxes_by_offer(self, offer_id: int) -> List[Box]:
        try:
            response = self.boxes_table.query(
                IndexName='offer-index',
                KeyConditionExpression=Key('offer_id').eq(offer_id)
            )
            return [Box(**item) for item in response.get('Items', [])]
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
    def create_order(self, order: Order) -> bool:
        try:
            item = self._prepare_item(order.__dict__)
            self.orders_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating order: {e}")
            return False

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
                return Customer(**response['Item'])
            return None
        except Exception as e:
            print(f"Error getting customer: {e}")
            return None

    def get_box(self, box_id: str) -> Optional[Box]:
        try:
            response = self.boxes_table.get_item(Key={'box_id': box_id})
            if 'Item' in response:
                return Box(**response['Item'])
            return None
        except Exception as e:
            print(f"Error getting box: {e}")
            return None

    def update_order(self, order_id: str, updates: Dict[str, Any]) -> bool:
        try:
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
        try:
            response = self.customers_table.scan(
                FilterExpression='authorization_status = :status',
                ExpressionAttributeValues={':status': status}
            )
            return [Customer(**item) for item in response.get('Items', [])]
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
        try:
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