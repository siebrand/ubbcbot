"""Reading DynamoDB results that span several pages."""

from collections.abc import Callable
from typing import Any


def read_all_pages(read: Callable[..., dict], params: dict[str, Any]) -> list[dict[str, Any]]:
    """Every item of a scan or query. DynamoDB returns at most 1 MB per call, so this follows LastEvaluatedKey.

    ``read`` is a table's ``scan`` or ``query``; ``params`` are its arguments.
    """
    items: list[dict[str, Any]] = []
    while True:
        response = read(**params)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            return items
        params = {**params, "ExclusiveStartKey": response["LastEvaluatedKey"]}
