"""Tests for paari.webhooks.hmac — Shopify webhook HMAC verification."""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod

import pytest


def test_hmac_verify_valid_signature() -> None:
    from paari.webhooks.hmac import verify_shopify_hmac

    secret = b"test-secret-key"
    body = b'{"id": 123, "title": "Test Order"}'
    computed = base64.b64encode(
        hmac_mod.new(secret, body, hashlib.sha256).digest()
    ).decode("utf-8")

    # Patch settings to use our test secret
    import paari.config

    original_secret = paari.config.settings.shopify_client_secret
    paari.config.settings.shopify_client_secret = "test-secret-key"
    try:
        assert verify_shopify_hmac(body, computed) is True
    finally:
        paari.config.settings.shopify_client_secret = original_secret


def test_hmac_verify_invalid_signature() -> None:
    from paari.webhooks.hmac import verify_shopify_hmac

    body = b'{"id": 123}'
    import paari.config

    original_secret = paari.config.settings.shopify_client_secret
    paari.config.settings.shopify_client_secret = "test-secret-key"
    try:
        assert verify_shopify_hmac(body, "badsignature") is False
    finally:
        paari.config.settings.shopify_client_secret = original_secret


def test_hmac_verify_empty_header() -> None:
    from paari.webhooks.hmac import verify_shopify_hmac

    import paari.config

    original_secret = paari.config.settings.shopify_client_secret
    paari.config.settings.shopify_client_secret = "test-secret-key"
    try:
        assert verify_shopify_hmac(b"{}", "") is False
    finally:
        paari.config.settings.shopify_client_secret = original_secret


def test_hmac_module_importable() -> None:
    from paari.webhooks.hmac import verify_shopify_hmac

    assert callable(verify_shopify_hmac)
