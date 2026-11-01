import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from boto3.dynamodb.conditions import Key
from repositories.base_repository import BaseRepository
from models.entities import Box

logger = logging.getLogger(__name__)

class BoxRepository(BaseRepository):
    def __init__(self):
        super().__init__("boxes")

    def create_box(self, box: Box) -> Optional[Box]:
        try:
            item = self._prepare_item(box.__dict__)
            self.table.put_item(Item=item)
            return box
        except Exception as e:
            logger.error(f"Error creating box: {e}")
            return None

    def get_box(self, box_id: str) -> Optional[Box]:
        try:
            response = self.table.get_item(Key={'box_id': box_id})
            if 'Item' in response:
                item = response['Item']
                if 'current_quantity' in item:
                    item['current_quantity'] = int(item['current_quantity'])
                if 'max_capacity' in item:
                    item['max_capacity'] = int(item['max_capacity'])
                return Box(**item)
            return None
        except Exception as e:
            logger.error(f"Error getting box: {e}")
            return None

    def get_boxes_by_offer(self, offer_id: int) -> List[Box]:
        try:
            response = self.table.query(
                IndexName='offer-index',
                KeyConditionExpression=Key('offer_id').eq(offer_id)
            )
            boxes = []
            for item in response.get('Items', []):
                if 'current_quantity' in item:
                    item['current_quantity'] = int(item['current_quantity'])
                if 'max_capacity' in item:
                    item['max_capacity'] = int(item['max_capacity'])
                boxes.append(Box(**item))
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

    def get_all_boxes(self) -> List[Box]:
        """Scan all boxes with minimal fields"""
        try:
            response = self.table.scan(
                ProjectionExpression='box_id, offer_id, current_quantity, max_capacity, #status',
                ExpressionAttributeNames={'#status': 'status'}
            )
            boxes = []
            for item in response.get('Items', []):
                item['current_quantity'] = int(item['current_quantity'])
                item['max_capacity'] = int(item['max_capacity'])
                boxes.append(Box(**item))
            return boxes
        except Exception as e:
            logger.error(f"Error getting all boxes: {e}")
            return []

    def update_box(self, box_id: str, updates: Dict[str, Any]) -> bool:
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
                Key={'box_id': box_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            logger.error(f"Error updating box: {e}")
            return False

    def delete_box(self, box_id: str) -> bool:
        try:
            self.table.delete_item(Key={'box_id': box_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting box: {e}")
            return False
