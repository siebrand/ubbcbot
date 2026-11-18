import logging
from datetime import UTC, datetime, timedelta

from models.entities import EditContext
from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class EditContextRepository(BaseRepository):
    def __init__(self):
        super().__init__("edit-contexts")

    def _contexts_for_chat(self, chat_id: int) -> list[dict]:
        """All raw context items of a chat (follows pagination)"""
        return self._scan_items(FilterExpression="chat_id = :chat_id", ExpressionAttributeValues={":chat_id": chat_id})

    def create_edit_context(self, context: EditContext) -> bool:
        """Store a context. A chat has at most one: a new prompt replaces any older one, so two open prompts
        can never be mixed up (the answer always belongs to the latest prompt)."""
        try:
            for old in self._contexts_for_chat(context.chat_id):
                if old.get("context_id") != context.context_id:
                    self.delete_edit_context(old["context_id"])

            item = self._prepare_item(context.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error creating edit context: {e}")
            return False

    def get_edit_context_by_chat_id(self, chat_id: int) -> EditContext | None:
        try:
            items = self._contexts_for_chat(chat_id)
            if not items:
                return None

            # Normally there is one. If an older leftover exists, the latest prompt wins.
            item = max(items, key=lambda i: str(i.get("created_at", "")))
            if "created_at" in item and isinstance(item["created_at"], str):
                item["created_at"] = datetime.fromisoformat(item["created_at"])
            return EditContext(**item)
        except Exception as e:
            logger.error(f"Error getting edit context: {e}")
            return None

    def delete_edit_context(self, context_id: str) -> bool:
        try:
            self.table.delete_item(Key={"context_id": context_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting edit context: {e}")
            return False

    def cleanup_old_edit_contexts(self) -> int:
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=1)

            items = self._scan_items(
                FilterExpression="created_at < :cutoff", ExpressionAttributeValues={":cutoff": cutoff_time.isoformat()}
            )

            deleted_count = 0
            for item in items:
                if self.delete_edit_context(item["context_id"]):
                    deleted_count += 1

            return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up edit contexts: {e}")
            return 0
