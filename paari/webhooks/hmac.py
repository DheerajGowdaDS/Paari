"""Shopify webhook HMAC-SHA256 verification.

Verifies X-Shopify-Hmac-SHA256 header using SHOPIFY_CLIENT_SECRET.
Uses timing-safe comparison to prevent timing attacks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

_log = logging.getLogger("paari.webhooks.hmac")


def verify_shopify_hmac(body: bytes, hmac_header: str) -> bool:
    """Verify the Shopify webhook HMAC-SHA256 signature.

    Args:
        body: Raw request body bytes.
        hmac_header: Value of X-Shopify-Hmac-SHA256 header.

    Returns:
        True if the signature is valid.
    """
    from paari.config import settings

    secret = settings.shopify_client_secret.encode("utf-8")
    computed = base64.b64encode(
        hmac.new(secret, body, hashlib.sha256).digest()
    ).decode("utf-8")

    if not hmac.compare_digest(computed, hmac_header):
        _log.warning("HMAC verification failed")
        return False
    return True
