from typing import Optional
from datetime import datetime, UTC, timedelta
from repositories.base_repository import BaseRepository
from models.entities import EditContext

class EditContextRepository(BaseRepository):
    def __init__(self):
        super().__init__("edit-contexts")

    def create_edit_context(self, context: EditContext) -> bool:
        try:
            item = self._prepare_item(context.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating edit context: {e}")
            return False

    def get_edit_context_by_chat_id(self, chat_id: int) -> Optional[EditContext]:
        try:
            response = self.table.scan(
                FilterExpression='chat_id = :chat_id',
                ExpressionAttributeValues={':chat_id': chat_id}
            )
            
            if response['Items']:
                item = response['Items'][0]
                if 'created_at' in item and isinstance(item['created_at'], str):
                    item['created_at'] = datetime.fromisoformat(item['created_at'])
                return EditContext(**item)
            return None
        except Exception as e:
            print(f"Error getting edit context: {e}")
            return None

    def delete_edit_context(self, context_id: str) -> bool:
        try:
            self.table.delete_item(Key={'context_id': context_id})
            return True
        except Exception as e:
            print(f"Error deleting edit context: {e}")
            return False

    def cleanup_old_edit_contexts(self) -> int:
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=1)
            
            response = self.table.scan(
                FilterExpression='created_at < :cutoff',
                ExpressionAttributeValues={':cutoff': cutoff_time.isoformat()}
            )
            
            deleted_count = 0
            for item in response.get('Items', []):
                if self.delete_edit_context(item['context_id']):
                    deleted_count += 1
            
            return deleted_count
        except Exception as e:
            print(f"Error cleaning up edit contexts: {e}")
            return 0
