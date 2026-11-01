import logging
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
from boto3.dynamodb.conditions import Key
from repositories.base_repository import BaseRepository
from models.entities import CustomerCredit, CreditTransaction

logger = logging.getLogger(__name__)

class CreditRepository(BaseRepository):
    def __init__(self):
        super().__init__("customer-credits")
        self.transactions_table = self.dynamodb.Table(f"{self.table_prefix}-credit-transactions")

    def _item_to_credit(self, item: dict) -> CustomerCredit:
        """Convert DynamoDB item to CustomerCredit, handling datetime conversion"""
        for field in ['last_updated', 'created_at']:
            if field in item and isinstance(item[field], str):
                item[field] = datetime.fromisoformat(item[field])
        return CustomerCredit(**item)

    def _item_to_transaction(self, item: dict) -> CreditTransaction:
        """Convert DynamoDB item to CreditTransaction, handling datetime conversion"""
        if 'created_at' in item and isinstance(item['created_at'], str):
            item['created_at'] = datetime.fromisoformat(item['created_at'])
        return CreditTransaction(**item)

    def create_customer_credit(self, credit: CustomerCredit) -> bool:
        try:
            item = self._prepare_item(credit.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error creating customer credit: {e}")
            return False

    def get_customer_credit(self, customer_id: str) -> Optional[CustomerCredit]:
        try:
            response = self.table.get_item(Key={'customer_id': customer_id})
            if 'Item' in response:
                return self._item_to_credit(response['Item'])
            return None
        except Exception as e:
            logger.error(f"Error getting customer credit: {e}")
            return None

    def update_customer_credit(self, customer_id: str, updates: Dict[str, Any]) -> bool:
        try:
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = self._serialize_datetime(value)
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.table.update_item(
                Key={'customer_id': customer_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            logger.error(f"Error updating customer credit: {e}")
            return False

    def create_credit_transaction(self, transaction: CreditTransaction) -> bool:
        try:
            item = self._prepare_item(transaction.__dict__)
            self.transactions_table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error creating credit transaction: {e}")
            return False

    def get_credit_transactions_by_customer(self, customer_id: str, limit: int = 50) -> List[CreditTransaction]:
        try:
            response = self.transactions_table.query(
                IndexName='customer-index',
                KeyConditionExpression=Key('customer_id').eq(customer_id),
                Limit=limit,
                ScanIndexForward=False
            )
            return [self._item_to_transaction(item) for item in response.get('Items', [])]
        except Exception as e:
            logger.error(f"Error getting credit transactions: {e}")
            return []

    def get_customers_with_credit_balance(self, min_amount: Optional[Decimal] = None) -> List[CustomerCredit]:
        try:
            if min_amount:
                response = self.table.scan(
                    FilterExpression='current_balance >= :min_amount',
                    ExpressionAttributeValues={':min_amount': min_amount}
                )
            else:
                response = self.table.scan()
            
            return [self._item_to_credit(item) for item in response.get('Items', [])]
        except Exception as e:
            logger.error(f"Error getting customers with credit balance: {e}")
            return []
