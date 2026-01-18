from typing import Optional, List, Dict, Any
from boto3.dynamodb.conditions import Key
from repositories.base_repository import BaseRepository
from models.entities import Order

class OrderRepository(BaseRepository):
    def __init__(self):
        super().__init__("orders")

    def create_order(self, order: Order) -> Optional[Order]:
        try:
            item = self._prepare_item(order.__dict__)
            self.table.put_item(Item=item)
            return order
        except Exception as e:
            print(f"Error creating order: {e}")
            return None

    def get_order(self, order_id: str) -> Optional[Order]:
        try:
            response = self.table.get_item(Key={'order_id': order_id})
            if 'Item' in response:
                return Order(**response['Item'])
            return None
        except Exception as e:
            print(f"Error getting order: {e}")
            return None

    def get_orders_by_customer(self, customer_id: str) -> List[Order]:
        try:
            response = self.table.query(
                IndexName='customer-index',
                KeyConditionExpression=Key('customer_id').eq(customer_id)
            )
            return [Order(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting orders by customer: {e}")
            return []

    def get_orders_by_offer(self, offer_id: int) -> List[Order]:
        try:
            response = self.table.query(
                IndexName='offer-index',
                KeyConditionExpression=Key('offer_id').eq(offer_id)
            )
            return [Order(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting orders by offer: {e}")
            return []

    def get_orders_by_box(self, box_id: str) -> List[Order]:
        try:
            response = self.table.scan(
                FilterExpression='box_id = :box_id',
                ExpressionAttributeValues={':box_id': box_id}
            )
            return [Order(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting orders by box: {e}")
            return []

    def get_all_orders(self, statuses: List[str] = None) -> List[Order]:
        try:
            if statuses:
                filter_expr = ' OR '.join([f'#status = :status{i}' for i in range(len(statuses))])
                expr_values = {f':status{i}': status for i, status in enumerate(statuses)}
                response = self.table.scan(
                    ProjectionExpression='order_id, offer_id, quantity, #status, customer_id, box_id, unit_price, total_price',
                    FilterExpression=filter_expr,
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues=expr_values
                )
            else:
                response = self.table.scan(
                    ProjectionExpression='order_id, offer_id, quantity, #status, customer_id, box_id, unit_price, total_price',
                    ExpressionAttributeNames={'#status': 'status'}
                )
            return [Order(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error getting all orders: {e}")
            return []

    def update_order(self, order_id: str, updates: Dict[str, Any]) -> bool:
        try:
            from datetime import datetime, UTC
            updates = updates.copy()
            updates['update_date'] = datetime.now(UTC).isoformat()
            
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.table.update_item(
                Key={'order_id': order_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            print(f"Error updating order: {e}")
            return False

    def delete_order(self, order_id: str) -> bool:
        try:
            self.table.delete_item(Key={'order_id': order_id})
            return True
        except Exception as e:
            print(f"Error deleting order: {e}")
            return False
