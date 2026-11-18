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

    def _query_all(self, params: dict) -> list[OrderHistory]:
        """Run a query and follow LastEvaluatedKey, so a result over 1 MB is not cut off"""
        items: list[dict] = []
        while True:
            response = self.table.query(**params)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            params["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [self._item_to_history(item) for item in items]

    def get_events_by_customer(
        self, customer_id: str, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> list[OrderHistory]:
        """Events of one customer, oldest first, via the customer-index (hash customer_id, range changed_at).

        Without dates every event is returned; with dates only those between them (both inclusive).

        Database errors are raised, not turned into an empty list: right after the index is added to a
        table with data it is still backfilling and cannot be read, and the data export must fail
        then instead of delivering an export without purchase history.
        """
        try:
            condition = Key("customer_id").eq(customer_id)
            if start_date or end_date:
                condition = condition & Key("changed_at").between(*self._range(start_date, end_date))
            return self._query_all({"IndexName": "customer-index", "KeyConditionExpression": condition})
        except Exception as e:
            logger.error(f"Error getting events by customer: {e}")
            raise

    def get_events_by_type(
        self,
        event_type: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        strict: bool = False,
    ) -> list[OrderHistory]:
        """Query all events of a type in a date range (both inclusive) via the event-time-index.

        Index: hash = event_type, range = changed_at (ISO-8601 string). ``strict`` re-raises database
        errors instead of returning an empty list, for reports that must not show "nothing" after a failed read.
        """
        try:
            condition = Key("event_type").eq(event_type) & Key("changed_at").between(*self._range(start_date, end_date))
            return self._query_all({"IndexName": "event-time-index", "KeyConditionExpression": condition})
        except Exception as e:
            logger.error(f"Error getting events by type: {e}")
            if strict:
                raise
            return []

    @staticmethod
    def _range(start_date: datetime | None, end_date: datetime | None) -> tuple[str, str]:
        """The changed_at bounds as stored: UTC ISO-8601 strings. Defaults: 2020-01-01 and now."""
        start = (start_date or datetime(2020, 1, 1, tzinfo=UTC)).astimezone(UTC)
        end = (end_date or datetime.now(UTC)).astimezone(UTC)
        return start.isoformat(), end.isoformat()
