import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from models.entities import CreditTransaction, CustomerCredit, OrderStatus
from repositories.base_repository import BaseRepository
from utils.dynamodb import read_all_pages

logger = logging.getLogger(__name__)


class CreditBalanceChanged(Exception):
    """The balance was changed by another write after it was read: read it again"""


class CreditRepository(BaseRepository):
    def __init__(self):
        super().__init__("customer-credits")
        self.transactions_table = self.dynamodb.Table(f"{self.table_prefix}-credit-transactions")

    def _item_to_credit(self, item: dict) -> CustomerCredit:
        """Convert DynamoDB item to CustomerCredit, handling datetime conversion"""
        for field in ["last_updated", "created_at"]:
            if field in item and isinstance(item[field], str):
                item[field] = datetime.fromisoformat(item[field])
        return CustomerCredit(**item)

    def _item_to_transaction(self, item: dict) -> CreditTransaction:
        """Convert DynamoDB item to CreditTransaction, handling datetime conversion"""
        if "created_at" in item and isinstance(item["created_at"], str):
            item["created_at"] = datetime.fromisoformat(item["created_at"])
        return CreditTransaction(**item)

    def create_customer_credit(self, credit: CustomerCredit) -> bool:
        try:
            item = self._prepare_item(credit.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error creating customer credit: {e}")
            return False

    def get_customer_credit(self, customer_id: str, strict: bool = False) -> CustomerCredit | None:
        """Get the credit record. ``strict`` re-raises database errors instead of returning None,
        for callers (the data export) that must not mistake a failed read for "no credit record"."""
        try:
            response = self.table.get_item(Key={"customer_id": customer_id})
            if "Item" in response:
                return self._item_to_credit(response["Item"])
            return None
        except Exception as e:
            logger.error(f"Error getting customer credit: {e}")
            if strict:
                raise
            return None

    def update_customer_credit(self, customer_id: str, updates: dict[str, Any]) -> bool:
        try:
            update_expression = "SET "
            expression_values = {}
            expression_names = {}

            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = self._serialize_datetime(value)
                expression_names[f"#{key}"] = key

            update_expression = update_expression.rstrip(", ")

            self.table.update_item(
                Key={"customer_id": customer_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating customer credit: {e}")
            return False

    def record_change(
        self,
        transaction: CreditTransaction,
        issued_delta: Decimal,
        used_delta: Decimal,
        now: str,
        order_credits: dict[str, Decimal] | None = None,
        order_items: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Write the transaction and move the balance from its balance_before to its balance_after, in one
        transaction: both or neither.

        The balance must still be the balance_before that was read (no record counts as 0); when another write
        changed it in the meantime, CreditBalanceChanged is raised and nothing is written, so the caller can read
        again. Returns False when the write failed for another reason.

        ``order_credits`` (order id → credit used for it) are written in the same transaction, each only while the
        order awaits payment and has no credit applied yet: credit is never used twice for one order. When one of
        them no longer qualifies, nothing is written and False is returned. ``order_items`` are other order writes
        (with their own conditions) that belong to the change, such as a new price (OrderRepository.price_item).
        """
        credit_items = [
            {
                "Update": {
                    "TableName": f"{self.table_prefix}-orders",
                    "Key": {"order_id": {"S": order_id}},
                    "UpdateExpression": "SET credit_applied = :credit",
                    "ConditionExpression": (
                        "#status = :awaiting AND (attribute_not_exists(credit_applied) OR credit_applied = :zero)"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":credit": {"N": str(credit)},
                        ":awaiting": {"S": OrderStatus.AWAITING_PAYMENT.value},
                        ":zero": {"N": "0"},
                    },
                }
            }
            for order_id, credit in (order_credits or {}).items()
        ]
        serializer = TypeSerializer()
        transaction_item = {k: serializer.serialize(v) for k, v in self._prepare_item(transaction.__dict__).items()}
        balance_condition = "current_balance = :before"
        if transaction.balance_before == 0:
            balance_condition = f"attribute_not_exists(current_balance) OR {balance_condition}"

        # A plain low-level client, as in OrderRepository.create_with_box_increment
        client = boto3.client("dynamodb")
        try:
            client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.transactions_table.name,
                            "Item": transaction_item,
                            "ConditionExpression": "attribute_not_exists(transaction_id)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": {"customer_id": {"S": transaction.customer_id}},
                            "UpdateExpression": (
                                "ADD current_balance :bd, total_credits_issued :id, total_credits_used :ud "
                                "SET last_updated = :now, created_at = if_not_exists(created_at, :now)"
                            ),
                            "ConditionExpression": balance_condition,
                            "ExpressionAttributeValues": {
                                ":bd": {"N": str(transaction.balance_after - transaction.balance_before)},
                                ":id": {"N": str(issued_delta)},
                                ":ud": {"N": str(used_delta)},
                                ":now": {"S": now},
                                ":before": {"N": str(transaction.balance_before)},
                            },
                        }
                    },
                    *credit_items,
                    *(order_items or []),
                ]
            )
            return True
        except ClientError as e:
            reasons = [r.get("Code") for r in e.response.get("CancellationReasons", [])]
            # The items are the transaction, the balance, then the orders: only the balance is worth a new read
            if len(reasons) > 1 and reasons[1] == "ConditionalCheckFailed":
                logger.warning(f"Credit balance of {transaction.customer_id} changed while it was being changed")
                raise CreditBalanceChanged(transaction.customer_id) from e
            logger.error(f"Credit change failed for {transaction.customer_id}: {e.response['Error']['Code']}")
            return False
        except Exception as e:
            logger.error(f"Credit change failed for {transaction.customer_id}: {type(e).__name__}")
            return False

    def create_credit_transaction(self, transaction: CreditTransaction) -> bool:
        try:
            item = self._prepare_item(transaction.__dict__)
            self.transactions_table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error creating credit transaction: {e}")
            return False

    def get_credit_transactions_by_customer(self, customer_id: str, limit: int = 50) -> list[CreditTransaction]:
        try:
            response = self.transactions_table.query(
                IndexName="customer-index",
                KeyConditionExpression=Key("customer_id").eq(customer_id),
                Limit=limit,
                ScanIndexForward=False,
            )
            return [self._item_to_transaction(item) for item in response.get("Items", [])]
        except Exception as e:
            logger.error(f"Error getting credit transactions: {e}")
            return []

    def get_all_credit_transactions_by_customer(self, customer_id: str) -> list[CreditTransaction]:
        """Every credit transaction of a customer, oldest first (no limit, follows pagination).

        Database errors are raised, not turned into an empty list: the data export must fail
        instead of silently leaving transactions out.
        """
        try:
            params = {
                "IndexName": "customer-index",
                "KeyConditionExpression": Key("customer_id").eq(customer_id),
            }
            items = read_all_pages(self.transactions_table.query, params)
            transactions = [self._item_to_transaction(item) for item in items]
            return sorted(transactions, key=lambda t: str(t.created_at))
        except Exception as e:
            logger.error(f"Error getting all credit transactions: {e}")
            raise

    def get_customers_with_credit_balance(
        self, min_amount: Decimal | None = None, strict: bool = False
    ) -> list[CustomerCredit]:
        """The credit records with at least ``min_amount``; without it every record, negative and zero balances
        included. A failed read is an empty list, or raised with ``strict`` (so "nobody" and "failed" differ)."""
        try:
            if min_amount:
                items = self._scan_items(
                    FilterExpression="current_balance >= :min_amount",
                    ExpressionAttributeValues={":min_amount": min_amount},
                )
            else:
                items = self._scan_items()

            return [self._item_to_credit(item) for item in items]
        except Exception as e:
            logger.error(f"Error getting customers with credit balance: {type(e).__name__}")
            if strict:
                raise
            return []
