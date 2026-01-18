from typing import Optional, List, Dict, Any
from boto3.dynamodb.conditions import Key
from repositories.base_repository import BaseRepository
from models.entities import Box

class BoxRepository(BaseRepository):
    def __init__(self):
        super().__init__("boxes")

    def create_box(self, box: Box) -> Optional[Box]:
        try:
            item = self._prepare_item(box.__dict__)
            self.table.put_item(Item=item)
            return box
        except Exception as e:
            print(f"Error creating box: {e}")
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
            print(f"Error getting box: {e}")
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
            return boxes
        except Exception as e:
            print(f"Error getting boxes by offer: {e}")
            return []

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
            print(f"Error getting all boxes: {e}")
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
            print(f"Error updating box: {e}")
            return False

    def delete_box(self, box_id: str) -> bool:
        try:
            self.table.delete_item(Key={'box_id': box_id})
            return True
        except Exception as e:
            print(f"Error deleting box: {e}")
            return False
