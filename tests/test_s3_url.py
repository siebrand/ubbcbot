"""Tests for the host-based S3 URL helpers (CodeQL incomplete-URL-sanitization fix)."""

import pytest

from utils.s3_url import extract_s3_key, is_s3_url


class TestIsS3Url:
    @pytest.mark.parametrize(
        "url",
        [
            "https://my-bucket.s3.amazonaws.com/offers/1/a.jpg",
            "https://my-bucket.s3.eu-north-1.amazonaws.com/offers/1/a.jpg",
            "https://ubbc-bot-test-123-images.s3.amazonaws.com/offers/37/x.jpg",
        ],
    )
    def test_accepts_real_s3_hosts(self, url):
        assert is_s3_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            # marker only in the path or query, not the host
            "https://evil.com/?x=s3.amazonaws.com",
            "https://evil.com/s3.amazonaws.com/a.jpg",
            # look-alike host that merely ends with the brand
            "https://s3.amazonaws.com.evil.com/a.jpg",
            "https://my-bucket.s3.amazonaws.com.evil.com/a.jpg",
            # not S3 at all / junk
            "https://example.com/a.jpg",
            "https://amazonaws.com/a.jpg",
            "not a url",
            "",
            None,
        ],
    )
    def test_rejects_spoofed_or_non_s3(self, url):
        assert is_s3_url(url) is False


class TestExtractS3Key:
    def test_extracts_key_from_valid_url(self):
        assert extract_s3_key("https://b.s3.amazonaws.com/offers/1/a.jpg") == "offers/1/a.jpg"

    def test_extracts_key_with_region_host(self):
        assert extract_s3_key("https://b.s3.eu-north-1.amazonaws.com/offers/2/y.jpg") == "offers/2/y.jpg"

    def test_returns_none_for_spoofed_host(self):
        assert extract_s3_key("https://s3.amazonaws.com.evil.com/offers/1/a.jpg") is None

    def test_returns_none_for_non_s3(self):
        assert extract_s3_key("https://example.com/offers/1/a.jpg") is None

    def test_returns_none_when_no_key(self):
        assert extract_s3_key("https://b.s3.amazonaws.com/") is None
