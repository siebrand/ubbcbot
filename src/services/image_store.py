"""Offer images in S3: upload, a temporary link to show one, and removal of all images of an offer.

The bucket is private: images are sent to Telegram as presigned URLs (see utils/s3_url.py for which URLs are ours).
"""

import logging
import os

import boto3

from utils.s3_url import extract_s3_key

logger = logging.getLogger(__name__)


class ImageStore:
    def __init__(self, s3=None, bucket: str | None = None):
        self.s3 = s3 or boto3.client("s3")
        table_prefix = os.environ.get("DYNAMODB_TABLE_PREFIX", "ubbc-bot-test")
        self.bucket = bucket or os.environ.get("S3_BUCKET_NAME", f"{table_prefix}-images")

    @staticmethod
    def _offer_prefix(offer_id: int) -> str:
        return f"offers/{offer_id}/"

    def upload(self, file_content: bytes, file_name: str, offer_id: int) -> str | None:
        """Store an image of an offer and return its URL (None when the upload failed)"""
        try:
            key = self._offer_prefix(offer_id) + file_name
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=file_content, ContentType="image/jpeg")
            return f"https://{self.bucket}.s3.amazonaws.com/{key}"
        except Exception as e:
            logger.error(f"Error uploading image to S3: {e}")
            return None

    def presigned_url(self, s3_url: str, expiration: int = 3600) -> str | None:
        """A link that shows the image for ``expiration`` seconds; None for a URL that is not one of ours"""
        try:
            # Extract key from S3 URL (host-validated, not a substring match)
            key = extract_s3_key(s3_url)
            if key is None:
                return None
            return self.s3.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expiration
            )
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

    def delete_offer_images(self, offer_id: int) -> bool:
        """Remove every image of an offer. A listing returns at most 1000 keys, so this follows every page."""
        try:
            pages = self.s3.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=self._offer_prefix(offer_id)
            )
            for page in pages:
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})
            return True
        except Exception as e:
            logger.error(f"Error deleting offer images: {e}")
            return False
