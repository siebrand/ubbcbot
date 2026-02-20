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

    def batch_get_orders(self, order_ids: List[str]) -> List[Order]:
        """Batch fetch orders using batch_get_item. Returns list of orders."""
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb')
            orders = []
            
            # Process in batches of 100 (DynamoDB limit)
            for i in range(0, len(order_ids), 100):
                batch = order_ids[i:i + 100]
                response = dynamodb.batch_get_item(
                    RequestItems={
                        self.table.name: {
                            'Keys': [{'order_id': oid} for oid in batch]
                        }
                    }
                )
                items = response.get('Responses', {}).get(self.table.name, [])
                orders.extend([Order(**item) for item in items])
            
            return orders
        except Exception as e:
            print(f"Error batch getting orders: {e}")
            return []

    def batch_update_order_status(self, order_ids: List[str], status: str) -> int:
        """Batch update order status using UpdateExpression. Returns count of successful updates."""
        try:
            from datetime import datetime, UTC
            
            updated_count = 0
            update_date = datetime.now(UTC).isoformat()
            
            # Process in smaller batches to avoid throttling
            for i in range(0, len(order_ids), 10):
                batch = order_ids[i:i + 10]
                
                for order_id in batch:
                    try:
                        self.table.update_item(
                            Key={'order_id': order_id},
                            UpdateExpression='SET #status = :status, #update_date = :update_date',
                            ExpressionAttributeNames={
                                '#status': 'status',
                                '#update_date': 'update_date'
                            },
                            ExpressionAttributeValues={
                                ':status': status,
                                ':update_date': update_date
                            }
                        )
                        updated_count += 1
                    except Exception as batch_error:
                        print(f"Batch update error for {order_id}: {batch_error}")
            
            return updated_count
        except Exception as e:
            print(f"Error in batch update: {e}")
            return 0
