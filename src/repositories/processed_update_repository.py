import logging
import time
from botocore.exceptions import ClientError
from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)

# How long a processed update_id is remembered before the TTL reaps it.
# A few hours comfortably covers Telegram's retry window after a 5xx/timeout.
_RETENTION_SECONDS = 6 * 60 * 60


class ProcessedUpdateRepository(BaseRepository):
    def __init__(self):
        super().__init__("processed-updates")

    def mark_processed(self, update_id: int) -> bool:
        """Record an update_id as processed; return True if this is the first time.

        A conditional PutItem (attribute_not_exists) makes the write succeed only
        once per update_id. If Telegram re-delivers the same update (after a 500 or
        a timeout), the second call hits the condition and returns False, so the
        caller can skip reprocessing and avoid duplicate orders. A TTL attribute
        lets DynamoDB reap old markers automatically.

        Fails open (returns True) on unexpected errors so a dedup-store outage does
        not silently drop legitimate updates.
        """
        try:
            self.table.put_item(
                Item={'update_id': str(update_id), 'ttl': int(time.time()) + _RETENTION_SECONDS},
                ConditionExpression='attribute_not_exists(update_id)',
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.info(f"Duplicate update_id {update_id} ignored")
                return False
            logger.error(f"Error marking update {update_id} processed: {e}")
            return True
        except Exception as e:
            logger.error(f"Error marking update {update_id} processed: {e}")
            return True
