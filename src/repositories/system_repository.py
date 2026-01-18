from typing import Optional
from src.repositories.base_repository import BaseRepository

class SystemRepository(BaseRepository):
    def __init__(self):
        super().__init__("counters")

    def get_next_id(self, counter_name: str) -> int:
        """Get next auto-incrementing ID for a specific counter"""
        try:
            response = self.table.update_item(
                Key={'counter_name': counter_name},
                UpdateExpression='ADD #val :inc',
                ExpressionAttributeNames={'#val': 'value'},
                ExpressionAttributeValues={':inc': 1},
                ReturnValues='UPDATED_NEW'
            )
            return int(response['Attributes']['value'])
        except Exception as e:
            print(f"Error getting next ID for {counter_name}: {e}")
            # Initialize counter if it doesn't exist
            try:
                self.table.put_item(
                    Item={'counter_name': counter_name, 'value': 1},
                    ConditionExpression='attribute_not_exists(counter_name)'
                )
                return 1
            except Exception:
                # Concurrency edge case, try update again or return 1
                return 1
