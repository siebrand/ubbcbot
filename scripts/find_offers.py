#!/usr/bin/env python3
"""
Find offers eligible for cleanup.

Usage:
    python scripts/find_offers.py <environment> <query>

Arguments:
    environment: test or prod
    query: empty | completed_paid | inactive | all
"""

import sys
import boto3


def scan_all(table, **kwargs):
    response = table.scan(**kwargs)
    items = response.get('Items', [])
    while 'LastEvaluatedKey' in response:
        response = table.scan(**kwargs, ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))
    return items


def find_empty(offers_table, boxes_table, orders_table):
    """Offers with no orders and no boxes."""
    box_offer_ids = {item['offer_id'] for item in scan_all(boxes_table, ProjectionExpression='offer_id')}
    order_offer_ids = {item['offer_id'] for item in scan_all(orders_table, ProjectionExpression='offer_id')}

    offers = scan_all(offers_table, ProjectionExpression='offer_id, #n, #s',
                      ExpressionAttributeNames={'#n': 'name', '#s': 'status'})

    results = [o for o in offers if o['offer_id'] not in box_offer_ids and o['offer_id'] not in order_offer_ids]

    if not results:
        print("No offers found without boxes and orders.")
        return

    print(f"Offers with no boxes and no orders ({len(results)}):\n")
    print(f"{'ID':<6} {'Status':<12} {'Name'}")
    print(f"{'--':<6} {'------':<12} {'----'}")
    for o in sorted(results, key=lambda x: x['offer_id']):
        print(f"{o['offer_id']:<6} {o.get('status', '?'):<12} {o.get('name', '?')}")


def find_completed_paid(offers_table, boxes_table, orders_table):
    """Completed offers with only paid orders or no orders at all."""
    offers = {o['offer_id']: o.get('name', '?') for o in scan_all(
        offers_table, ProjectionExpression='offer_id, #n',
        FilterExpression='#s = :completed',
        ExpressionAttributeNames={'#n': 'name', '#s': 'status'},
        ExpressionAttributeValues={':completed': 'completed'}
    )}

    if not offers:
        print("No completed offers found.")
        return

    orders = scan_all(orders_table, ProjectionExpression='offer_id, #s', ExpressionAttributeNames={'#s': 'status'})

    offer_orders = {oid: [] for oid in offers}
    for order in orders:
        oid = order['offer_id']
        if oid in offer_orders:
            offer_orders[oid].append(order.get('status', '?'))

    results = []
    for oid, statuses in offer_orders.items():
        if not statuses:
            results.append((oid, offers[oid], 0))
        elif all(s == 'completed' for s in statuses):
            results.append((oid, offers[oid], len(statuses)))

    if not results:
        print("No completed offers with only paid orders found.")
        return

    print(f"Completed offers with only paid orders ({len(results)}):\n")
    print(f"{'ID':<6} {'Orders':<8} {'Name'}")
    print(f"{'--':<6} {'------':<8} {'----'}")
    for oid, name, count in sorted(results):
        print(f"{oid:<6} {count:<8} {name}")


def find_inactive(offers_table, boxes_table, orders_table):
    """Offers with inactive status."""
    offers = scan_all(offers_table, ProjectionExpression='offer_id, #n',
                      FilterExpression='#s = :inactive',
                      ExpressionAttributeNames={'#n': 'name', '#s': 'status'},
                      ExpressionAttributeValues={':inactive': 'inactive'})

    if not offers:
        print("No inactive offers found.")
        return

    print(f"Inactive offers ({len(offers)}):\n")
    print(f"{'ID':<6} {'Name'}")
    print(f"{'--':<6} {'----'}")
    for o in sorted(offers, key=lambda x: x['offer_id']):
        print(f"{o['offer_id']:<6} {o.get('name', '?')}")


QUERIES = {
    'empty': find_empty,
    'completed_paid': find_completed_paid,
    'inactive': find_inactive,
}


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('test', 'prod'):
        print("Usage: python scripts/find_offers.py <test|prod> <empty|completed_paid|inactive|all>")
        sys.exit(1)

    environment = sys.argv[1]
    query = sys.argv[2] if len(sys.argv) > 2 else 'all'

    dynamodb = boto3.resource('dynamodb')
    prefix = f'ubbc-bot-{environment}'
    offers_table = dynamodb.Table(f'{prefix}-offers')
    boxes_table = dynamodb.Table(f'{prefix}-boxes')
    orders_table = dynamodb.Table(f'{prefix}-orders')

    if query == 'all':
        for name, fn in QUERIES.items():
            print(f"=== {name} ===\n")
            fn(offers_table, boxes_table, orders_table)
            print()
    elif query in QUERIES:
        QUERIES[query](offers_table, boxes_table, orders_table)
    else:
        print(f"Unknown query: {query}. Available: empty, completed_paid, inactive, all")
        sys.exit(1)
