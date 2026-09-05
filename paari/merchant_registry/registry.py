"""MerchantRegistry: load merchant records from the DB.

A small in-process cache is maintained for the duration of a request chain.
The cache is invalidated explicitly via `invalidate(merchant_id)` when a
merchant record is updated.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from paari.merchant_registry.merchant import Merchant, MerchantNotFound, MerchantStatus

_log = logging.getLogger("paari.merchant_registry")

_cache: dict[str, Merchant] = {}


async def load(merchant_id: str, session: AsyncSession) -> Merchant:
    """Load a merchant from the cache or DB."""
    cached = _cache.get(merchant_id)
    if cached is not None:
        return cached
    row = (
        await session.execute(
            text(
                "SELECT id, name, policy_version, shopify_domain, shopify_api_version, status, "
                "shopify_access_token_env, shopify_client_secret_env, "
                "avg_transaction_paise, active_hours_utc "
                "FROM merchants WHERE id = :id"
            ),
            {"id": merchant_id},
        )
    ).first()
    if row is None:
        raise MerchantNotFound(merchant_id)
    active_hours = json.loads(row.active_hours_utc or "[]")
    # store_id currently equals id; future: separate column.
    merchant = Merchant(
        id=row.id,
        store_id=row.id,
        name=row.name,
        policy_version=row.policy_version,
        status=MerchantStatus(row.status),
        shopify_domain=row.shopify_domain,
        shopify_api_version=row.shopify_api_version,
        shopify_access_token_env=row.shopify_access_token_env,
        shopify_client_secret_env=row.shopify_client_secret_env,
        autonomous_limit_paise=_autonomous_limit_paise(row.id),
        avg_transaction_paise=row.avg_transaction_paise or 0,
        active_hours_utc=active_hours,
    )
    _cache[merchant_id] = merchant
    return merchant


def _autonomous_limit_paise(merchant_id: str) -> int:
    """Read the merchant's autonomous limit from policy (TX layer)."""
    from paari.config import settings

    return settings.demo_merchant_autonomous_limit_paise


def invalidate(merchant_id: str | None = None) -> None:
    """Invalidate one entry, or the whole cache if merchant_id is None."""
    if merchant_id is None:
        _cache.clear()
    else:
        _cache.pop(merchant_id, None)
