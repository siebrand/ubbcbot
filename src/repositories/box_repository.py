import logging
from datetime import datetime
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from models.entities import Box
from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BoxRepository(BaseRepository):
    def __init__(self):
        super().__init__("boxes")

    def create_box(self, box: Box) -> Box | None:
        try:
            item = self._prepare_item(box.__dict__)
            self.table.put_item(Item=item)
            return box
        except Exception as e:
            logger.error(f"Error creating box: {e}")
            return None

    def get_box(self, box_id: str) -> Box | None:
        try:
            response = self.table.get_item(Key={"box_id": box_id})
            if "Item" in response:
                return self._item_to_box(response["Item"])
            return None
        except Exception as e:
            logger.error(f"Error getting box: {e}")
            return None

    @staticmethod
    def _item_to_box(item: dict[str, Any]) -> Box:
        """DynamoDB returns numbers as Decimal; the quantities are plain ints"""
        if "current_quantity" in item:
            item["current_quantity"] = int(item["current_quantity"])
        if "max_capacity" in item:
            item["max_capacity"] = int(item["max_capacity"])
        return Box(**item)

    def get_boxes_by_offer(self, offer_id: int) -> list[Box]:
        try:
            items = self._query_items(IndexName="offer-index", KeyConditionExpression=Key("offer_id").eq(offer_id))
            boxes = [self._item_to_box(item) for item in items]
            # Always return boxes in creation-time ascending order.
            # created_at is stored as an ISO 8601 string (lexicographically
            # sortable); normalize to string so a mix of str/datetime is safe.
            boxes.sort(key=lambda b: self._created_at_sort_key(b.created_at))
            return boxes
        except Exception as e:
            logger.error(f"Error getting boxes by offer: {e}")
            return []

    @staticmethod
    def _created_at_sort_key(created_at: Any) -> str:
        """Normalize created_at (str or datetime) to a sortable ISO string."""
        if isinstance(created_at, datetime):
            return created_at.isoformat()
        return str(created_at) if created_at is not None else ""

    def get_all_boxes(self) -> list[Box]:
        """Scan all boxes with minimal fields"""
        try:
            items = self._scan_items(
                ProjectionExpression="box_id, offer_id, current_quantity, max_capacity, #status, created_at",
                ExpressionAttributeNames={"#status": "status"},
            )
            return [self._item_to_box(item) for item in items]
        except Exception as e:
            logger.error(f"Error getting all boxes: {e}")
            return []

    def get_boxes_by_status(self, status: str) -> list[Box]:
        """All boxes with this status. The table has no status index, so this is a (paginated) scan."""
        try:
            items = self._scan_items(FilterExpression=Attr("status").eq(status))
            return [self._item_to_box(item) for item in items]
        except Exception as e:
            logger.error(f"Error getting {status} boxes: {e}")
            return []

    def increment_box_quantity(self, box_id: str, delta: int, max_capacity: int) -> bool:
        """Atomically add `delta` to current_quantity, failing if it would exceed max_capacity (see
        add_to_box_quantity). Returns True on success, False if the condition failed or on error."""
        return self.add_to_box_quantity(box_id, delta, max_capacity) is not None

    def add_to_box_quantity(self, box_id: str, delta: int, max_capacity: int) -> int | None:
        """Atomically add `delta` to current_quantity, failing if it would exceed max_capacity.

        Uses a single conditional UpdateItem so concurrent orders cannot overfill a box:
        the ADD and the capacity check happen server-side in one operation. `delta` may be
        negative (e.g. on cancellation); the guard only limits the upper bound.

        Returns the quantity the box holds after this change (so a status can follow the
        quantity this write left, not a read from before it), or None if the condition
        failed (would overfill) or on error.
        """
        from botocore.exceptions import ClientError

        try:
            # DynamoDB condition expressions cannot do arithmetic, so compute the
            # threshold in Python: current_quantity must be <= max_capacity - delta
            # for the post-increment value to stay within capacity. For a negative
            # delta (cancellation) the threshold grows, making the guard a no-op.
            response = self.table.update_item(
                Key={"box_id": box_id},
                UpdateExpression="ADD current_quantity :delta",
                ConditionExpression="attribute_exists(box_id) AND current_quantity <= :threshold",
                ExpressionAttributeValues={":delta": delta, ":threshold": max_capacity - delta},
                ReturnValues="UPDATED_NEW",
            )
            return int(response["Attributes"]["current_quantity"])
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(f"Box {box_id} increment by {delta} rejected: would exceed capacity {max_capacity}")
                return None
            logger.error(f"Error incrementing box {box_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error incrementing box {box_id}: {e}")
            return None

    def mark_full_if_at_capacity(self, box_id: str) -> bool:
        """OPEN → FULL, only while the box is open and holds its capacity at the time of the write"""
        return self._set_status_if(box_id, "open", "full", "current_quantity >= max_capacity")

    def reopen_if_below_capacity(self, box_id: str) -> bool:
        """FULL → OPEN, only while the box is full and holds less than its capacity at the time of the write. An
        ORDERED or DELIVERED box is never reopened."""
        return self._set_status_if(box_id, "full", "open", "current_quantity < max_capacity")

    def _set_status_if(self, box_id: str, from_status: str, to_status: str, quantity_condition: str) -> bool:
        """Set the status on condition of the current status and the live quantity; False when the condition failed"""
        from botocore.exceptions import ClientError

        try:
            self.table.update_item(
                Key={"box_id": box_id},
                UpdateExpression="SET #status = :to",
                ConditionExpression=f"#status = :from AND {quantity_condition}",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":from": from_status, ":to": to_status},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                logger.error(f"Error setting box {box_id} to {to_status}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting box {box_id} to {to_status}: {type(e).__name__}")
            return False

    def update_box(self, box_id: str, updates: dict[str, Any]) -> bool:
        try:
            update_expression = "SET "
            expression_values = {}
            expression_names = {}

            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key

            update_expression = update_expression.rstrip(", ")

            self.table.update_item(
                Key={"box_id": box_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating box: {e}")
            return False

    def delete_box_if_empty(self, box_id: str, statuses: tuple[str, ...]) -> bool:
        """Delete the box only while it holds nothing and is in one of ``statuses``; False when it was not deleted"""
        from botocore.exceptions import ClientError

        values: dict[str, Any] = {":zero": 0, **{f":status_{i}": s for i, s in enumerate(statuses)}}
        in_statuses = ", ".join(f":status_{i}" for i in range(len(statuses)))
        try:
            self.table.delete_item(
                Key={"box_id": box_id},
                ConditionExpression=f"current_quantity = :zero AND #status IN ({in_statuses})",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues=values,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(f"Box {box_id} was not deleted: it is no longer empty")
                return False
            logger.error(f"Error deleting box {box_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting box {box_id}: {type(e).__name__}")
            return False

    def delete_box(self, box_id: str) -> bool:
        try:
            self.table.delete_item(Key={"box_id": box_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting box: {e}")
            return False
