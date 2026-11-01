"""Tests for the atomic order + box-increment transaction.

moto 5.1.x cannot execute transact_write_items (it raises an internal
TypeError for any TransactItems payload), so these tests drive the real
DynamoDBService but stub the low-level client's transact_write_items to assert
(a) the exact single-transaction payload we send and (b) how the method
handles success vs a cancelled transaction. The payload shape is what makes the
order Put and the capacity-guarded box Update atomic on real DynamoDB.
"""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from services.database import DynamoDBService
from models.entities import Order, OrderStatus


@pytest.fixture
def db(dynamodb):
    service = DynamoDBService()
    # Stub only the transaction call; everything else uses moto.
    service.dynamodb.meta.client.transact_write_items = MagicMock()
    return service


def _order():
    return Order(customer_id="c1", box_id="tb-1", offer_id=1, quantity=2,
                 unit_price=Decimal('5.00'), total_price=Decimal('10.00'),
                 status=OrderStatus.PENDING.value)


class TestCreateOrderWithBoxIncrement:
    def test_sends_single_atomic_transaction(self, db):
        order = _order()

        result = db.create_order_with_box_increment(order, "tb-1", 2, 12)

        assert result is order
        db.dynamodb.meta.client.transact_write_items.assert_called_once()
        items = db.dynamodb.meta.client.transact_write_items.call_args.kwargs['TransactItems']

        # Exactly two items in one transaction: order Put + box Update.
        assert len(items) == 2
        put, update = items[0]['Put'], items[1]['Update']

        # Order Put: guarded against id collision, carries the order's box_id.
        assert put['TableName'].endswith('-orders')
        assert put['ConditionExpression'] == 'attribute_not_exists(order_id)'
        assert put['Item']['order_id']['S'] == order.order_id
        assert put['Item']['box_id']['S'] == 'tb-1'

        # Box Update: atomic ADD guarded so the post-increment stays within capacity.
        assert update['TableName'].endswith('-boxes')
        assert update['Key']['box_id']['S'] == 'tb-1'
        assert update['UpdateExpression'] == 'ADD current_quantity :delta'
        assert update['ConditionExpression'] == 'attribute_exists(box_id) AND current_quantity <= :threshold'
        assert update['ExpressionAttributeValues'][':delta']['N'] == '2'
        # threshold = max_capacity - quantity = 12 - 2
        assert update['ExpressionAttributeValues'][':threshold']['N'] == '10'

    def test_cancelled_transaction_returns_none(self, db):
        db.dynamodb.meta.client.transact_write_items.side_effect = ClientError(
            {'Error': {'Code': 'TransactionCanceledException', 'Message': 'cancelled'}},
            'TransactWriteItems',
        )

        result = db.create_order_with_box_increment(_order(), "tb-1", 2, 12)

        assert result is None

    def test_threshold_tracks_quantity(self, db):
        """A larger order lowers the capacity threshold accordingly."""
        db.create_order_with_box_increment(_order(), "tb-1", 5, 12)

        items = db.dynamodb.meta.client.transact_write_items.call_args.kwargs['TransactItems']
        update = items[1]['Update']
        assert update['ExpressionAttributeValues'][':delta']['N'] == '5'
        assert update['ExpressionAttributeValues'][':threshold']['N'] == '7'  # 12 - 5
