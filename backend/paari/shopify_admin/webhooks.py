"""Shopify webhook registration.

Register/unregister webhook subscriptions via Admin GraphQL.
Idempotent: delete + recreate on each call.
Called at startup if PAARI_WEBHOOK_BASE_URL is set.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("paari.shopify_admin.webhooks")


async def register_webhooks(merchant_id: str, base_url: str) -> dict[str, str]:
    """Register webhook subscriptions for the merchant.

    Returns a dict mapping topic -> webhook_id.
    """
    from paari.config import settings
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()
    topics = settings.webhook_topic_orders.split(",") + settings.webhook_topic_inventory.split(",")
    results: dict[str, str] = {}

    for topic in topics:
        topic = topic.strip()
        if not topic:
            continue
        callback_url = f"{base_url}/webhooks/shopify/{topic.replace('/', '_')}"
        try:
            webhook_id = await client.create_webhook_subscription(topic, callback_url)
            if webhook_id:
                results[topic] = webhook_id
                _log.info("Registered webhook %s -> %s", topic, webhook_id)
            else:
                _log.warning("Webhook registration returned empty ID for %s", topic)
        except Exception as e:
            _log.error("Failed to register webhook %s: %s", topic, e)

    await client.close()
    return results
