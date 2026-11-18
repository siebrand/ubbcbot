"""Offer images in the private S3 bucket."""

import boto3
import pytest
from moto import mock_aws

from services.image_store import ImageStore

BUCKET = "ubbc-bot-test-images"


@pytest.fixture
def store(aws_credentials):
    with mock_aws():
        s3 = boto3.client("s3", region_name="eu-west-1")
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})
        yield ImageStore(s3=s3, bucket=BUCKET)


def keys(store) -> list[str]:
    return sorted(o["Key"] for o in store.s3.list_objects_v2(Bucket=BUCKET).get("Contents", []))


def test_an_upload_is_stored_under_the_offer_and_returns_its_url(store):
    url = store.upload(b"jpeg", "a.jpg", 7)

    assert url == f"https://{BUCKET}.s3.amazonaws.com/offers/7/a.jpg"
    assert keys(store) == ["offers/7/a.jpg"]


def test_a_presigned_url_for_one_of_our_images(store):
    url = store.presigned_url(f"https://{BUCKET}.s3.amazonaws.com/offers/7/a.jpg", expiration=60)

    assert url.startswith(f"https://{BUCKET}.s3.amazonaws.com/offers/7/a.jpg?")
    assert "Expires=" in url or "X-Amz-Expires=60" in url


def test_no_presigned_url_for_another_host(store):
    assert store.presigned_url("https://evil.example/offers/7/a.jpg") is None


def test_deleting_removes_every_image_of_the_offer_and_only_those(store):
    for i in range(3):
        store.upload(b"x", f"{i}.jpg", 7)
    store.upload(b"x", "keep.jpg", 70)

    assert store.delete_offer_images(7) is True

    assert keys(store) == ["offers/70/keep.jpg"]


def test_deleting_follows_every_page_of_the_listing(store):
    for i in range(5):
        store.upload(b"x", f"{i}.jpg", 7)
    paginate = store.s3.get_paginator("list_objects_v2").paginate
    paginator = store.s3.get_paginator("list_objects_v2")
    paginator.paginate = lambda **kw: paginate(PaginationConfig={"PageSize": 2}, **kw)
    store.s3.get_paginator = lambda name: paginator

    assert store.delete_offer_images(7) is True
    assert keys(store) == []


def test_an_offer_without_images(store):
    assert store.delete_offer_images(8) is True


def test_a_failed_upload(store):
    store.bucket = "does-not-exist"

    assert store.upload(b"x", "a.jpg", 7) is None
    assert store.delete_offer_images(7) is False
