import logging
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from models.entities import Order
from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)

# Global secondary indexes of the orders table (template.yaml)
STATUS_INDEX = "status-index"
BOX_INDEX = "box-index"

INDEX_UNAVAILABLE_CODES = ("ValidationException", "ResourceNotFoundException")


class OrderRepository(BaseRepository):
    def __init__(self):
        super().__init__("orders")

    def _query_index(
        self,
        index_name: str,
        key_name: str,
        value: Any,
        projection: str | None = None,
        names: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """The items whose ``key_name`` equals ``value``, read through the index ``index_name``.

        While the index does not exist yet or is still being built (the deploy that adds it), the same items are
        found with a scan: slower, but the same answer, so a deploy never makes a list come out empty.
        Every other database error is raised.
        """
        params: dict[str, Any] = {
            "ExpressionAttributeNames": {"#key": key_name, **(names or {})},
            "ExpressionAttributeValues": {":value": value},
        }
        if projection:
            params["ProjectionExpression"] = projection
        try:
            response = self.table.query(IndexName=index_name, KeyConditionExpression="#key = :value", **params)
        except ClientError as e:
            error = e.response.get("Error", {})
            # DynamoDB says "ValidationException: The table does not have the specified index" or "Cannot read from
            # backfilling global secondary index"; the test database says "ResourceNotFoundException: Invalid index".
            # The index name in the message keeps a missing table or other errors out of this.
            index_unavailable = error.get("Code") in INDEX_UNAVAILABLE_CODES and index_name in error.get("Message", "")
            if not index_unavailable:
                raise
            logger.warning(f"Index {index_name} is not available yet, scanning the table instead: {error['Message']}")
            response = self.table.scan(FilterExpression="#key = :value", **params)
        return response.get("Items", [])

    def create_order(self, order: Order) -> Order | None:
        try:
            item = self._prepare_item(order.__dict__)
            self.table.put_item(Item=item)
            return order
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return None

    def get_order(self, order_id: str) -> Order | None:
        try:
            response = self.table.get_item(Key={"order_id": order_id})
            if "Item" in response:
                return Order(**response["Item"])
            return None
        except Exception as e:
            logger.error(f"Error getting order: {e}")
            return None

    def get_orders_by_customer(self, customer_id: str, strict: bool = False) -> list[Order]:
        """Orders of a customer. ``strict`` re-raises database errors instead of returning an empty list,
        for callers (the data export) that must not mistake a failed read for "no orders"."""
        try:
            # Follow pagination: a data export must contain every order, not just the first 1 MB
            params: dict[str, Any] = {
                "IndexName": "customer-index",
                "KeyConditionExpression": Key("customer_id").eq(customer_id),
            }
            items: list[dict[str, Any]] = []
            while True:
                response = self.table.query(**params)
                items.extend(response.get("Items", []))
                if "LastEvaluatedKey" not in response:
                    break
                params["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            return [Order(**item) for item in items]
        except Exception as e:
            logger.error(f"Error getting orders by customer: {e}")
            if strict:
                raise
            return []

    def get_orders_by_offer(self, offer_id: int) -> list[Order]:
        try:
            response = self.table.query(IndexName="offer-index", KeyConditionExpression=Key("offer_id").eq(offer_id))
            return [Order(**item) for item in response.get("Items", [])]
        except Exception as e:
            logger.error(f"Error getting orders by offer: {e}")
            return []

    def get_orders_by_box(self, box_id: str) -> list[Order]:
        try:
            return [Order(**item) for item in self._query_index(BOX_INDEX, "box_id", box_id)]
        except Exception as e:
            logger.error(f"Error getting orders by box: {e}")
            return []

    def get_orders_by_status(self, status: str) -> list[Order]:
        """All orders with this status, whatever the offer, box or customer"""
        try:
            return [Order(**item) for item in self._query_index(STATUS_INDEX, "status", status)]
        except Exception as e:
            logger.error(f"Error getting orders by status: {e}")
            return []

    def get_all_orders(self, statuses: list[str] | None = None) -> list[Order]:
        projection = "order_id, offer_id, quantity, #status, customer_id, box_id, unit_price, total_price"
        try:
            if statuses:
                items: list[dict[str, Any]] = []
                for status in dict.fromkeys(statuses):  # each status once, in the order given
                    items.extend(self._query_index(STATUS_INDEX, "status", status, projection, {"#status": "status"}))
            else:
                response = self.table.scan(
                    ProjectionExpression=projection,
                    ExpressionAttributeNames={"#status": "status"},
                )
                items = response.get("Items", [])
            return [Order(**item) for item in items]
        except Exception as e:
            logger.error(f"Error getting all orders: {e}")
            return []

    def update_order(self, order_id: str, updates: dict[str, Any]) -> bool:
        try:
            from datetime import UTC, datetime

            updates = updates.copy()
            updates["update_date"] = datetime.now(UTC).isoformat()

            update_expression = "SET "
            expression_values = {}
            expression_names = {}

            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key

            update_expression = update_expression.rstrip(", ")

            self.table.update_item(
                Key={"order_id": order_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating order: {e}")
            return False

    def delete_order(self, order_id: str) -> bool:
        try:
            self.table.delete_item(Key={"order_id": order_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting order: {e}")
            return False

    def batch_get_orders(self, order_ids: list[str]) -> list[Order]:
        """Batch fetch orders using batch_get_item. Returns list of orders."""
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            orders = []

            # Process in batches of 100 (DynamoDB limit)
            for i in range(0, len(order_ids), 100):
                batch = order_ids[i : i + 100]
                response = dynamodb.batch_get_item(
                    RequestItems={self.table.name: {"Keys": [{"order_id": oid} for oid in batch]}}
                )
                items = response.get("Responses", {}).get(self.table.name, [])
                orders.extend([Order(**item) for item in items])

            return orders
        except Exception as e:
            logger.error(f"Error batch getting orders: {e}")
            return []

    def batch_update_order_status(self, order_ids: list[str], status: str) -> int:
        """Batch update order status using UpdateExpression. Returns count of successful updates."""
        try:
            from datetime import UTC, datetime

            updated_count = 0
            update_date = datetime.now(UTC).isoformat()

            # Process in smaller batches to avoid throttling
            for i in range(0, len(order_ids), 10):
                batch = order_ids[i : i + 10]

                for order_id in batch:
                    try:
                        self.table.update_item(
                            Key={"order_id": order_id},
                            UpdateExpression="SET #status = :status, #update_date = :update_date",
                            ExpressionAttributeNames={"#status": "status", "#update_date": "update_date"},
                            ExpressionAttributeValues={":status": status, ":update_date": update_date},
                        )
                        updated_count += 1
                    except Exception as batch_error:
                        logger.error(f"Batch update error for {order_id}: {batch_error}")

            return updated_count
        except Exception as e:
            logger.error(f"Error in batch update: {e}")
            return 0
