import logging
from datetime import UTC, datetime
from typing import Any

from models.entities import DiscountPeriod, DiscountStatus
from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class DiscountRepository(BaseRepository):
    def __init__(self):
        super().__init__("discounts")

    def create_discount(self, discount: DiscountPeriod) -> bool:
        try:
            item = self._prepare_item(discount.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error creating discount: {e}")
            return False

    def get_active_discount(self) -> DiscountPeriod | None:
        try:
            now = datetime.now(UTC)
            response = self.table.scan(
                FilterExpression=(
                    "#status = :status AND start_time <= :now AND (attribute_not_exists(end_time) OR end_time > :now)"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": DiscountStatus.ACTIVE.value, ":now": now.isoformat()},
            )
            items = response.get("Items", [])
            if items:
                return DiscountPeriod(**items[0])
            return None
        except Exception as e:
            logger.error(f"Error getting active discount: {e}")
            return None

    def update_discount(self, discount_id: str, updates: dict[str, Any]) -> bool:
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
                Key={"discount_id": discount_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating discount: {e}")
            return False
