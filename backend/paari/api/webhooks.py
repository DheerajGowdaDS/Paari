"""Shopify webhook ingest endpoint.

POST /webhooks/shopify/{topic}
- Verifies HMAC-SHA256 signature
- Deduplicates via webhook_events unique constraint
- Enqueues for background processing
- Returns 200 immediately
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/shopify/{topic}")
async def shopify_webhook(
    topic: str,
    request: Request,
    x_shopify_hmac_sha256: str = Header(default=""),
    x_shopify_webhook_id: str = Header(default=""),
    x_shopify_shop_domain: str = Header(default=""),
) -> dict[str, str]:
    """Handle an incoming Shopify webhook."""
    from paari.webhooks.hmac import verify_shopify_hmac
    from paari.webhooks.queue import WEBHOOK_QUEUE, WebhookEvent

    # Read raw body
    body = await request.body()

    # Verify HMAC (deny-by-default: reject when header is missing in live mode)
    from paari.config import settings

    if settings.shopify_mode == "live":
        if not x_shopify_hmac_sha256:
            raise HTTPException(status_code=401, detail="Missing HMAC header")
        if not verify_shopify_hmac(body, x_shopify_hmac_sha256):
            raise HTTPException(status_code=401, detail="HMAC verification failed")
    elif x_shopify_hmac_sha256 and not verify_shopify_hmac(body, x_shopify_hmac_sha256):
        raise HTTPException(status_code=401, detail="HMAC verification failed")

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Generate event ID
    event_id = str(uuid.uuid4())
    webhook_id = x_shopify_webhook_id or str(uuid.uuid4())

    # Determine merchant_id from shop domain
    merchant_id = await _resolve_merchant_id(x_shopify_shop_domain)

    # Persist to webhook_events (dedup via unique constraint)
    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    try:
        async with maker() as session:
            await session.execute(
                text(
                    "INSERT INTO webhook_events (id, source, merchant_id, topic, webhook_id, payload_json, status) "
                    "VALUES (:id, :source, :mid, :topic, :wid, :payload, 'PENDING')"
                ),
                {
                    "id": event_id,
                    "source": "SHOPIFY",
                    "mid": merchant_id,
                    "topic": topic,
                    "wid": webhook_id,
                    "payload": json.dumps(payload),
                },
            )
            await session.commit()
    except Exception:
        # Duplicate webhook_id — already processed
        return {"status": "ok", "note": "duplicate"}

    # Enqueue for background processing
    event = WebhookEvent(
        event_id=event_id,
        source="SHOPIFY",
        merchant_id=merchant_id,
        topic=topic,
        webhook_id=webhook_id,
        payload=payload,
    )
    await WEBHOOK_QUEUE.put(event)

    return {"status": "ok"}


async def _resolve_merchant_id(shop_domain: str) -> str | None:
    """Resolve shop domain to merchant_id."""
    if not shop_domain:
        return None
    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text("SELECT id FROM merchants WHERE shopify_domain = :domain"),
                {"domain": shop_domain},
            )
        ).first()
        return row.id if row else None
