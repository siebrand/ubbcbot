import json
from typing import Any


def create_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Create standardized Lambda response"""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
