import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table_prefix = os.environ["DYNAMODB_TABLE_PREFIX"]
offers_table = dynamodb.Table(f"{table_prefix}-offers")
boxes_table = dynamodb.Table(f"{table_prefix}-boxes")
counters_table = dynamodb.Table(f"{table_prefix}-counters")

CACHE_KEY = "offers_api_cache"
CACHE_TTL = 3600


def _get_cache() -> dict | None:
    response = counters_table.get_item(Key={"counter_name": CACHE_KEY})
    item = response.get("Item")
    if item and int(item.get("expires_at", 0)) > int(time.time()):
        return json.loads(item["cached_response"])
    return None


def _set_cache(body: dict) -> None:
    counters_table.put_item(
        Item={
            "counter_name": CACHE_KEY,
            "cached_response": json.dumps(body),
            "expires_at": int(time.time()) + CACHE_TTL,
        }
    )


def _build_response(status_code: int, body: dict) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": f"max-age={CACHE_TTL}",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        cached = _get_cache()
        if cached:
            return _build_response(200, cached)

        # Scan active offers
        scan_resp = offers_table.scan(
            FilterExpression="#s = :active",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":active": "active"},
        )
        active_offers = sorted(scan_resp.get("Items", []), key=lambda o: int(o["offer_id"]))

        offers = []
        for offer in active_offers:
            offer_id = int(offer["offer_id"])

            boxes_resp = boxes_table.query(
                IndexName="offer-index",
                KeyConditionExpression=Key("offer_id").eq(offer_id),
            )
            remaining = sum(
                int(b["max_capacity"]) - int(b["current_quantity"])
                for b in boxes_resp.get("Items", [])
                if int(b["current_quantity"]) < int(b["max_capacity"])
            )

            offers.append(
                {
                    "offer_id": offer_id,
                    "name": offer.get("name", ""),
                    "price_per_unit": str(offer.get("price_per_unit", "0")),
                    "description": offer.get("description", ""),
                    "remaining_units": remaining,
                }
            )

        body = {
            "offers": offers,
            "cached_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        _set_cache(body)
        return _build_response(200, body)

    except Exception as e:
        logger.error(f"Error in offers API: {e}")
        return _build_response(500, {"error": "internal_error"})
