"""Discovery endpoint: agent card for external buyer agents.

GET /api/v1/merchants/{merchant_id}/agent-card — public, no auth.
Returns a JSON contract describing the merchant's AI capabilities,
policies, and restrictions.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["discovery"])


def _get_autonomous_limit(merchant_limit_paise: int | None) -> int:
    """Merchant's autonomous limit (what M-01 enforces); platform ceiling as fallback."""
    from paari.config import settings

    return merchant_limit_paise or settings.max_autonomous_transaction_paise


def _policy_cap_value(document_json: str | None, field: str) -> int | None:
    """Extract a merchant-policy numeric cap (e.g. tx.discount_pct -> M-02 value).

    Display-only: mirrors the values the policy engine enforces so the agent
    card never drifts from the deterministic rules.
    """
    if not document_json:
        return None
    try:
        import json as _json

        rules = _json.loads(document_json).get("rules", [])
    except Exception:
        return None
    for rule in rules:
        when = rule.get("when", {}) or {}
        if when.get("field") == field:
            try:
                return int(when.get("value"))
            except (TypeError, ValueError):
                return None
    return None


@router.get("/api/v1/merchants/{merchant_id}/agent-card")
async def agent_card(merchant_id: str) -> dict:
    """Return the merchant's agent card for external buyer agents."""
    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        # Load merchant
        row = (
            await session.execute(
                text(
                    "SELECT id, name, shopify_domain, status, policy_version, "
                    "avg_transaction_paise, active_hours_utc, autonomous_limit_paise "
                    "FROM merchants WHERE id = :id"
                ),
                {"id": merchant_id},
            )
        ).first()

        if row is None:
            raise HTTPException(status_code=404, detail="merchant_not_found")

        if row.status != "AI_TRANSACTABLE":
            raise HTTPException(status_code=404, detail="merchant_not_transactable")

        # Load store context
        ctx_row = (
            await session.execute(
                text("SELECT payload_json, fetched_at FROM store_contexts WHERE merchant_id = :mid"),
                {"mid": merchant_id},
            )
        ).first()

        # Load policy
        policy_row = (
            await session.execute(
                text(
                    "SELECT version FROM policies WHERE merchant_id = :mid AND is_active = 1 "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"mid": merchant_id},
            )
        ).first()
        merchant_policy_row = (
            await session.execute(
                text(
                    "SELECT document_json FROM policies WHERE merchant_id = :mid "
                    "AND layer = 'MERCHANT' AND is_active = 1 "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"mid": merchant_id},
            )
        ).first()

    # Parse context
    import json

    policies_default = {
        "shipping": {
            "international": False,
            "free_threshold_paise": 0,
            "estimate_days": "5-7 business days",
        },
        "returns": {"window_days": 30, "conditions": "Unworn items with original tags"},
    }
    if ctx_row:
        ctx_data = json.loads(ctx_row.payload_json)
        policies = ctx_data.get("policies", policies_default)
        fetched_at = ctx_row.fetched_at
    else:
        policies = policies_default
        fetched_at = None

    policy_version = policy_row.version if policy_row else "v1"
    merchant_doc = merchant_policy_row[0] if merchant_policy_row else None
    max_discount = _policy_cap_value(merchant_doc, "tx.discount_pct") or 10
    max_quantity = _policy_cap_value(merchant_doc, "tx.quantity") or 5

    return {
        "merchant_id": row.id,
        "store_id": row.id,
        "store_name": row.name,
        "store_url": row.shopify_domain,
        "status": row.status,
        "currency": "INR",
        "capabilities": [
            "catalog.read",
            "inventory.read",
            "product.read",
            "quote.create",
            "deal.negotiate",
            "payment.request",
        ],
        "restrictions": {
            "max_autonomous_transaction": _get_autonomous_limit(row.autonomous_limit_paise),
            "max_discount_percent": max_discount,
            "max_quantity_per_line_item": max_quantity,
            "max_items_per_order": 10,
            "min_order_value": 100,
            "max_order_value": 10000000,
            "international_shipping": policies["shipping"]["international"],
            "allowed_countries": ["IN"],
        },
        "policies": {
            "return_window_days": policies["returns"]["window_days"],
            "shipping_estimate": policies["shipping"]["estimate_days"],
            "free_shipping_threshold": policies["shipping"]["free_threshold_paise"],
        },
        "endpoints": {
            "negotiate": f"/api/v1/merchants/{row.id}/negotiate",
            "quote": f"/api/v1/merchants/{row.id}/quote",
            "checkout": f"/api/v1/merchants/{row.id}/checkout",
        },
        "policy_version": policy_version,
        "last_updated": fetched_at.isoformat() if hasattr(fetched_at, 'isoformat') else (str(fetched_at) if fetched_at else None),
    }
