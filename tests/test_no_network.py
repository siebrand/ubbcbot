"""Tests do not reach the network: a call that was not mocked fails the test (conftest.py, `network_attempts`)"""

import boto3
import pytest
import requests

from services.telegram_client import TelegramClient


def test_a_request_that_is_not_mocked_does_not_leave_the_machine(network_attempts):
    with pytest.raises(requests.ConnectionError):
        requests.get("https://api.telegram.org/bot123:abc/getMe", timeout=1)

    assert network_attempts, "the attempt is recorded, so the test fails"
    network_attempts.clear()


def test_a_telegram_call_that_is_not_mocked_is_recorded_although_the_client_swallows_the_error(network_attempts):
    assert not TelegramClient("123:abc").call("getMe").ok

    assert network_attempts
    network_attempts.clear()


def test_aws_outside_moto_does_not_leave_the_machine(network_attempts):
    with pytest.raises(Exception):  # noqa: B017 - whatever botocore makes of the refused connection
        boto3.client("ssm", region_name="eu-north-1").get_parameter(Name="/ubbc-bot/test/telegram-bot-token")

    assert network_attempts
    network_attempts.clear()


def test_moto_still_works(dynamodb, network_attempts):
    assert "ubbc-bot-test-orders" in boto3.client("dynamodb", region_name="eu-west-1").list_tables()["TableNames"]
    assert network_attempts == []
