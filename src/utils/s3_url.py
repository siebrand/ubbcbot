"""Helpers for safely recognising and parsing our S3 image URLs.

CodeQL flags `"s3.amazonaws.com" in url` as incomplete URL sanitization: the
substring can appear anywhere (e.g. `https://evil.com/?x=s3.amazonaws.com` or
`https://s3.amazonaws.com.evil.com/`), so it does not prove the URL points at
S3. These helpers parse the URL and validate the hostname instead.
"""

import re
from urllib.parse import urlparse

# Virtual-hosted-style S3 hostnames we produce / consume:
#   <bucket>.s3.amazonaws.com
#   <bucket>.s3.<region>.amazonaws.com   (e.g. bucket.s3.eu-north-1.amazonaws.com)
# Anchored match on the parsed hostname so look-alike hosts
# (…amazonaws.com.evil.com) and path/query markers are rejected.
_S3_HOST_RE = re.compile(r"^[a-z0-9.\-]+\.s3(\.[a-z0-9\-]+)?\.amazonaws\.com$")


def _s3_host(url: str) -> str:
    """Return the lowercased hostname of url, or '' if it cannot be parsed."""
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError, AttributeError:
        return ""


def is_s3_url(url: str) -> bool:
    """True only if url's hostname is an S3 virtual-hosted-style host.

    Validates the parsed hostname against an anchored pattern rather than
    searching for a substring, so a look-alike or attacker-controlled host
    (e.g. amazonaws.com.evil.com, or the marker sitting in the path/query) is
    correctly rejected.
    """
    if not url:
        return False
    return bool(_S3_HOST_RE.match(_s3_host(url)))


def extract_s3_key(url: str) -> str | None:
    """Return the S3 object key from a virtual-hosted-style S3 URL, else None.

    The key is the URL path without its leading slash; returns None when the
    URL is not an S3 URL or has no path.
    """
    if not is_s3_url(url):
        return None
    path = urlparse(url).path.lstrip("/")
    return path or None
