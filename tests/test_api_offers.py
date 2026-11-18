"""The public read-only API: GET /offers lists the active offers with the units still available."""

import importlib
import json
import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest


@pytest.fixture
def api(dynamodb, monkeypatch):
    """The module binds its tables on import, so it is (re)loaded inside the mocked AWS"""
    monkeypatch.setenv("DYNAMODB_TABLE_PREFIX", "ubbc-bot-test")
    import handlers.api.offers as offers

    offers = importlib.reload(offers)
    for offer_id, status in [(3, "active"), (1, "active"), (2, "draft")]:
        offers.offers_table.put_item(
            Item={
                "offer_id": offer_id,
                "name": f"Bier {offer_id}",
                "status": status,
                "price_per_unit": "1.75",
                "description": "<b>Fris</b>",
            }
        )
    for box_id, offer_id, quantity, capacity in [("a", 1, 10, 12), ("b", 1, 12, 12), ("c", 1, 0, 24), ("d", 3, 2, 6)]:
        offers.boxes_table.put_item(
            Item={"box_id": box_id, "offer_id": offer_id, "current_quantity": quantity, "max_capacity": capacity}
        )
    return offers


def body(response) -> dict:
    return json.loads(response["body"])


def test_active_offers_by_id_with_the_units_still_available(api):
    response = api.handler({}, None)

    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "application/json"
    assert [o["offer_id"] for o in body(response)["offers"]] == [1, 3]
    assert body(response)["offers"][0] == {
        "offer_id": 1,
        "name": "Bier 1",
        "price_per_unit": "1.75",
        "description": "<b>Fris</b>",
        "remaining_units": 2 + 24,  # the full box has nothing left
    }
    assert body(response)["offers"][1]["remaining_units"] == 4


def test_the_answer_is_cached_for_an_hour(api):
    first = body(api.handler({}, None))
    api.offers_table.delete_item(Key={"offer_id": 1})

    assert body(api.handler({}, None)) == first

    cached = api.counters_table.get_item(Key={"counter_name": api.CACHE_KEY})["Item"]
    assert int(cached["expires_at"]) > time.time() + api.CACHE_TTL - 60


def test_an_expired_cache_is_rebuilt(api):
    api.handler({}, None)
    api.counters_table.update_item(
        Key={"counter_name": api.CACHE_KEY},
        UpdateExpression="SET expires_at = :past",
        ExpressionAttributeValues={":past": 0},
    )
    api.offers_table.delete_item(Key={"offer_id": 1})

    assert [o["offer_id"] for o in body(api.handler({}, None))["offers"]] == [3]


def test_an_error_is_a_500_without_details(api):
    with patch.object(api, "_get_cache", side_effect=RuntimeError("secret detail")):
        response = api.handler({}, None)

    assert response["statusCode"] == 500
    assert body(response) == {"error": "internal_error"}


@contextmanager
def one_item_per_call(api):
    scan, query = api.offers_table.scan, api.boxes_table.query
    with (
        patch.object(api.offers_table, "scan", side_effect=lambda **kw: scan(Limit=1, **kw)),
        patch.object(api.boxes_table, "query", side_effect=lambda **kw: query(Limit=1, **kw)),
    ):
        yield


def test_every_page_of_offers_and_boxes_is_read(api):
    with one_item_per_call(api):
        offers = body(api.handler({}, None))["offers"]

    assert [(o["offer_id"], o["remaining_units"]) for o in offers] == [(1, 26), (3, 4)]
