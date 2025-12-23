import boto3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from boto3.dynamodb.conditions import Key
from models.entities import Supplier, Offer, Customer, Box, Order

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
            item = self._prepare_item(offer.__dict__)
            self.offers_table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating offer: {e}")
            return False

    def get_offer(self, offer_id: str) -> Optional[Offer]:
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

    def get_boxes_by_offer(self, offer_id: str) -> List[Box]:
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
                update_expression += f"{key} = :{key}, "
                expression_values[f":{key}"] = value
            
            update_expression = update_expression.rstrip(", ")
            
            self.boxes_table.update_item(
                Key={'box_id': box_id},
                UpdateExpression=update_expression,
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

    def get_orders_by_offer(self, offer_id: str) -> List[Order]:
        try:
            response = self.orders_table.query(
                IndexName='offer-index',
                KeyConditionExpression=Key('offer_id').eq(offer_id)
            )
            return [Order(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting orders by offer: {e}")
            return []

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
            
            for key, value in updates.items():
                update_expression += f"{key} = :{key}, "
                expression_values[f":{key}"] = value
            
            update_expression = update_expression.rstrip(", ")
            
            self.orders_table.update_item(
                Key={'order_id': order_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            print(f"Error updating order: {e}")
            return False