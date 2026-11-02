import logging
from dataclasses import fields
from datetime import UTC, datetime

from boto3.dynamodb.conditions import Key

from models.entities import OrderHistory
from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)

_HISTORY_FIELDS = {f.name for f in fields(OrderHistory)}


class OrderHistoryRepository(BaseRepository):
    def __init__(self):
        super().__init__("order-history")

    def _item_to_history(self, item: dict) -> OrderHistory:
        """Convert a DynamoDB item to OrderHistory.

        Tolerates legacy rows that still carry dropped attributes (order_id,
        customer_name, reason, composite keys, ...) by keeping only the fields
        the slim dataclass defines.
        """
        data = {k: v for k, v in item.items() if k in _HISTORY_FIELDS}
        if "changed_at" in data and isinstance(data["changed_at"], str):
            data["changed_at"] = datetime.fromisoformat(data["changed_at"])
        return OrderHistory(**data)

    def create_order_history(self, history: OrderHistory) -> bool:
        try:
            item = self._prepare_item(history.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error creating order history: {e}")
            return False

    def batch_create_order_history(self, histories: list[OrderHistory]) -> int:
        """Batch create order history records. Returns count of successful writes."""
        try:
            created_count = 0
            # Process in batches of 25 (DynamoDB batch_write limit)
            for i in range(0, len(histories), 25):
                batch = histories[i : i + 25]
                with self.table.batch_writer() as writer:
                    for history in batch:
                        item = self._prepare_item(history.__dict__)
                        writer.put_item(Item=item)
                        created_count += 1
            return created_count
        except Exception as e:
            logger.error(f"Error batch creating order history: {e}")
            return 0

    def get_events_by_type(
        self, event_type: str, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> list[OrderHistory]:
        """Query all events of a type in a date range via the event-time-index.

        Index: hash = event_type, range = changed_at (ISO-8601 string).
        """
        try:
            if not start_date:
                start_date = datetime(2020, 1, 1, tzinfo=UTC)
            if not end_date:
                end_date = datetime.now(UTC)

            response = self.table.query(
                IndexName="event-time-index",
                KeyConditionExpression=Key("event_type").eq(event_type)
                & Key("changed_at").between(start_date.isoformat(), end_date.isoformat()),
            )
            return [self._item_to_history(item) for item in response.get("Items", [])]
        except Exception as e:
            logger.error(f"Error getting events by type: {e}")
            return []
