import os
import sys

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"


@pytest.fixture(scope="function")
def dynamodb(aws_credentials):
    """Mocked DynamoDB client."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")

        # Create suppliers table
        dynamodb.create_table(
            TableName="ubbc-bot-test-suppliers",
            KeySchema=[{"AttributeName": "supplier_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "supplier_id", "AttributeType": "S"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create customers table
        dynamodb.create_table(
            TableName="ubbc-bot-test-customers",
            KeySchema=[{"AttributeName": "customer_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "customer_id", "AttributeType": "S"},
                {"AttributeName": "telegram_user_id", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "telegram-user-index",
                    "KeySchema": [{"AttributeName": "telegram_user_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                }
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create offers table
        dynamodb.create_table(
            TableName="ubbc-bot-test-offers",
            KeySchema=[{"AttributeName": "offer_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "offer_id", "AttributeType": "N"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create orders table
        dynamodb.create_table(
            TableName="ubbc-bot-test-orders",
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "customer_id", "AttributeType": "S"},
                {"AttributeName": "offer_id", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "customer-index",
                    "KeySchema": [{"AttributeName": "customer_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
                {
                    "IndexName": "offer-index",
                    "KeySchema": [{"AttributeName": "offer_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create boxes table
        dynamodb.create_table(
            TableName="ubbc-bot-test-boxes",
            KeySchema=[{"AttributeName": "box_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "box_id", "AttributeType": "S"},
                {"AttributeName": "offer_id", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "offer-index",
                    "KeySchema": [{"AttributeName": "offer_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                }
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create counters table
        dynamodb.create_table(
            TableName="ubbc-bot-test-counters",
            KeySchema=[{"AttributeName": "counter_name", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "counter_name", "AttributeType": "S"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create customer credits table
        dynamodb.create_table(
            TableName="ubbc-bot-test-customer-credits",
            KeySchema=[{"AttributeName": "customer_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "customer_id", "AttributeType": "S"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create credit transactions table
        dynamodb.create_table(
            TableName="ubbc-bot-test-credit-transactions",
            KeySchema=[{"AttributeName": "transaction_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "transaction_id", "AttributeType": "S"},
                {"AttributeName": "customer_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "customer-index",
                    "KeySchema": [{"AttributeName": "customer_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                }
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create order history table (purchase analytics event store)
        dynamodb.create_table(
            TableName="ubbc-bot-test-order-history",
            KeySchema=[{"AttributeName": "history_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "history_id", "AttributeType": "S"},
                {"AttributeName": "event_type", "AttributeType": "S"},
                {"AttributeName": "changed_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "event-time-index",
                    "KeySchema": [
                        {"AttributeName": "event_type", "KeyType": "HASH"},
                        {"AttributeName": "changed_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create notifications table
        dynamodb.create_table(
            TableName="ubbc-bot-test-notifications",
            KeySchema=[{"AttributeName": "notification_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "notification_id", "AttributeType": "S"},
                {"AttributeName": "offer_id", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "offer-index",
                    "KeySchema": [{"AttributeName": "offer_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                }
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create edit contexts table
        dynamodb.create_table(
            TableName="ubbc-bot-test-edit-contexts",
            KeySchema=[{"AttributeName": "context_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "context_id", "AttributeType": "S"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Create processed-updates table (idempotency dedup)
        dynamodb.create_table(
            TableName="ubbc-bot-test-processed-updates",
            KeySchema=[{"AttributeName": "update_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "update_id", "AttributeType": "S"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        yield dynamodb
