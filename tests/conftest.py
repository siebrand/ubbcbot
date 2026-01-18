import pytest
import os
import boto3
import sys
from moto import mock_aws

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

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
            KeySchema=[{'AttributeName': 'supplier_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'supplier_id', 'AttributeType': 'S'}],
            ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
        )
        
        yield dynamodb
