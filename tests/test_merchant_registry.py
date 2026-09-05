"""Tests for paari.merchant_registry — merchant identity and registry."""

from __future__ import annotations

import pytest

from paari.merchant_registry.merchant import Merchant, MerchantNotFound, MerchantStatus


def test_merchant_dataclass() -> None:
    m = Merchant(
        id="MER-TEST",
        store_id="MER-TEST",
        name="Test Store",
        policy_version="v1",
        status=MerchantStatus.AI_TRANSACTABLE,
        shopify_domain="test.myshopify.com",
    )
    assert m.id == "MER-TEST"
    assert m.status == MerchantStatus.AI_TRANSACTABLE


def test_merchant_status_values() -> None:
    assert MerchantStatus.AI_TRANSACTABLE.value == "AI_TRANSACTABLE"
    assert MerchantStatus.INACTIVE.value == "INACTIVE"
    assert MerchantStatus.SUSPENDED.value == "SUSPENDED"


def test_merchant_not_found_is_exception() -> None:
    with pytest.raises(MerchantNotFound):
        raise MerchantNotFound("missing-merchant")


def test_registry_module_importable() -> None:
    from paari.merchant_registry import Merchant, MerchantNotFound, MerchantStatus, invalidate, load

    assert callable(load)
    assert callable(invalidate)


def test_registry_invalidate() -> None:
    from paari.merchant_registry import registry as reg

    # Should not raise
    reg.invalidate("nonexistent")
    reg.invalidate(None)
