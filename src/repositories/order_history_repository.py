from typing import List, Optional
from datetime import datetime, UTC, timedelta
from boto3.dynamodb.conditions import Key
from repositories.base_repository import BaseRepository
from models.entities import OrderHistory

class OrderHistoryRepository(BaseRepository):
    def __init__(self):
        super().__init__("order-history")

    def _item_to_history(self, item: dict) -> OrderHistory:
        """Convert DynamoDB item to OrderHistory, handling datetime conversion"""
        if 'changed_at' in item and isinstance(item['changed_at'], str):
            item['changed_at'] = datetime.fromisoformat(item['changed_at'])
        return OrderHistory(**item)

    def create_order_history(self, history: OrderHistory) -> bool:
        try:
            item = self._prepare_item(history.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating order history: {e}")
            return False

    def get_order_history(self, order_id: str, limit: int = 50) -> List[OrderHistory]:
        try:
            response = self.table.query(
                IndexName='order-index',
                KeyConditionExpression=Key('order_id').eq(order_id),
                Limit=limit,
                ScanIndexForward=False
            )
            return [self._item_to_history(item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting order history: {e}")
            return []

    def get_customer_events(self, customer_id: str, event_type: Optional[str] = None, days: int = 30) -> List[OrderHistory]:
        try:
            cutoff_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()
            
            if event_type:
                customer_event = f"{customer_id}#{event_type}"
                response = self.table.query(
                    IndexName='customer-event-index',
                    KeyConditionExpression=Key('customer_event').eq(customer_event) & Key('changed_at').gte(cutoff_date)
                )
            else:
                response = self.table.scan(
                    FilterExpression='customer_id = :cid AND changed_at >= :cutoff',
                    ExpressionAttributeValues={
                        ':cid': customer_id,
                        ':cutoff': cutoff_date
                    }
                )
            
            return [self._item_to_history(item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting customer events: {e}")
            return []

    def get_events_by_type(self, event_type: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[OrderHistory]:
        try:
            if not start_date:
                start_date = datetime(2020, 1, 1, tzinfo=UTC)
            if not end_date:
                end_date = datetime.now(UTC)
            
            start_key = f"{event_type}#{start_date.isoformat()}"
            end_key = f"{event_type}#{end_date.isoformat()}"
            
            response = self.table.query(
                IndexName='event-date-index',
                KeyConditionExpression=Key('event_date').between(start_key, end_key)
            )
            
            return [self._item_to_history(item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting events by type: {e}")
            return []

    def get_history_by_customer_name(self, customer_name: str, event_type: Optional[str] = None, limit: int = 50) -> List[OrderHistory]:
        try:
            if event_type:
                key = f"{customer_name}#{event_type}"
                response = self.table.query(
                    IndexName='customer-name-event-index',
                    KeyConditionExpression=Key('customer_name_event').eq(key),
                    Limit=limit,
                    ScanIndexForward=False
                )
            else:
                response = self.table.query(
                    IndexName='customer-name-event-index',
                    KeyConditionExpression=Key('customer_name_event').begins_with(customer_name + '#'),
                    Limit=limit,
                    ScanIndexForward=False
                )
            
            return [self._item_to_history(item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting history by customer name: {e}")
            return []
