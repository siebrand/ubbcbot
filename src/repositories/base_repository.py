import os
from datetime import datetime
from typing import Any

import boto3

from utils.dynamodb import read_all_pages


class BaseRepository:
    def __init__(self, table_name_suffix: str):
        self.dynamodb = boto3.resource("dynamodb")
        self.table_prefix = os.environ.get("DYNAMODB_TABLE_PREFIX", "ubbc-bot-test")
        self.table_name = f"{self.table_prefix}-{table_name_suffix}"
        self.table = self.dynamodb.Table(self.table_name)

    def _scan_items(self, **params) -> list[dict[str, Any]]:
        """Every item of a scan. DynamoDB returns at most 1 MB per call, so this follows LastEvaluatedKey."""
        return read_all_pages(self.table.scan, params)

    def _query_items(self, **params) -> list[dict[str, Any]]:
        """Every item of a query, following LastEvaluatedKey like _scan_items"""
        return read_all_pages(self.table.query, params)

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
