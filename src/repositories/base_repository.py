import os
from datetime import datetime
from typing import Any

import boto3


class BaseRepository:
    def __init__(self, table_name_suffix: str):
        self.dynamodb = boto3.resource("dynamodb")
        self.table_prefix = os.environ.get("DYNAMODB_TABLE_PREFIX", "ubbc-bot-test")
        self.table_name = f"{self.table_prefix}-{table_name_suffix}"
        self.table = self.dynamodb.Table(self.table_name)

    def _prepare_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Prepare item for DynamoDB storage by converting datetimes and removing None values and empty strings"""
        prepared = {}
        for key, value in item.items():
            if isinstance(value, datetime):
                prepared[key] = value.isoformat()
            elif value is not None and value != "":
                prepared[key] = value
        return prepared

    def _serialize_datetime(self, obj: Any) -> Any:
        """Convert datetime objects to ISO strings"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj
