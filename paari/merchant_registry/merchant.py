"""Merchant dataclass + exceptions for the registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MerchantStatus(str, Enum):
    AI_TRANSACTABLE = "AI_TRANSACTABLE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class MerchantNotFound(Exception):
    """Raised when a merchant_id is not in the registry."""


class MerchantNotTransactable(Exception):
    """Raised when a merchant's status is not AI_TRANSACTABLE."""


@dataclass(frozen=True)
class Merchant:
    """A Paari merchant. Identity lives here; Shopify is one possible adapter."""

    id: str
    store_id: str
    name: str
    policy_version: str
    status: MerchantStatus
    shopify_domain: str | None
    shopify_api_version: str = "2025-01"
    shopify_access_token_env: str = "SHOPIFY_ADMIN_ACCESS_TOKEN"
    shopify_client_secret_env: str = "SHOPIFY_CLIENT_SECRET"
    autonomous_limit_paise: int = 0
    avg_transaction_paise: int = 0
    active_hours_utc: list[int] = field(default_factory=list)
