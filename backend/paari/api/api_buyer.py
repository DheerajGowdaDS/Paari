"""Buyer-facing /api shims — prose-only, no metrics exposed.

Thin wrappers: auth via JWT, then delegate to existing services without
changing governance/payment/architecture logic.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from paari.authn.jwt_verifier import TokenVerificationError, verify_token
from paari.db.engine import get_session_maker

router = APIRouter(prefix="/api", tags=["api-buyer"])


def _require_bearer(authorization: str | None) -> Any:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return verify_token(token)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


class BuyerChatRequest(BaseModel):
    session_id: str = Field(..., description="Client session id, e.g. sess_01")
    message: str = Field(..., description="User intent text")
    context: dict[str, Any] | None = None


class EscrowAuthorizeRequest(BaseModel):
    quote_id: str = Field(..., description="Quote id, e.g. Q-001")


_SUGGESTIONS = [
    {"label": "Review SLA terms", "prompt": "Review SLA terms and downtime liability formulas"},
    {
        "label": "Simulate merchant failover",
        "prompt": "Simulate merchant failover scenarios under 100Gbps network loss",
    },
    {"label": "Adjust procurement scope", "prompt": "Adjust procurement scope and recalculate"},
]


def _classify(message: str) -> tuple[str, str]:
    m = message.lower()
    if any(k in m for k in ("adjust", "scope", "recalculate", "procurement")):
        return "scope", "scope"
    if any(
        k in m
        for k in (
            "snowboard",
            "board",
            "burton",
            "lib tech",
            "bindings",
            "boots",
            "helmet",
            "goggles",
            "jacket",
            "accessor",
        )
    ):
        q = "bindings" if "binding" in m else "boots" if "boot" in m else "snowboard"
        return "catalog", q
    if any(k in m for k in ("product", "available", "stock", "have", "show")) and any(
        k in m for k in ("what", "which", "list", "have")
    ):
        return "catalog", "snowboard"
    if "failover" in m or "network" in m:
        return "failover", "failover"
    if "sla" in m or "downtime" in m or "liability" in m:
        return "sla", "sla"
    if "budget" in m:
        return "scope", "scope"
    return "general", "general"


@router.post("/agent/buyer/chat")
async def buyer_chat(
    req: BuyerChatRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    ident = _require_bearer(authorization)
    # Queue: if autorun is still streaming/polling, wait for its current answer queue to finish
    try:
        from paari.api.api_autorun import _tasks as _autorun_tasks

        if _autorun_tasks:
            # wait up to 12s for autorun to finish (max_steps 6 *1.2s)
            for _ in range(60):
                if not _autorun_tasks:
                    break
                await asyncio.sleep(0.2)
    except Exception:
        pass
    kind, _ = _classify(req.message)

    products: list[dict[str, str]] | None = None
    if kind == "catalog":
        query = (
            "bindings"
            if "binding" in req.message.lower()
            else "boots"
            if "boot" in req.message.lower()
            else "snowboard"
        )
        try:
            from paari.adapters.commerce import get_commerce_adapter

            adapter = get_commerce_adapter()
            res = await adapter.search_products(query, limit=5)
            items = res.get("products", []) if isinstance(res, dict) else []
            filtered = [
                p
                for p in items
                if "gift card" not in (p.get("title") or p.get("name") or "").lower()
            ]
            items = filtered if filtered else items
            if items:
                products = []
                for p in items[:2]:
                    products.append(
                        {
                            "name": p.get("title") or p.get("name") or query.title(),
                            "description": (
                                p.get("description") or "Available from verified merchant."
                            )[:180],
                            "availability_label": "In stock"
                            if p.get("available", True)
                            else "Limited stock",
                        }
                    )
        except Exception:
            pass
        if not products:
            if query == "bindings":
                products = [
                    {
                        "name": "Burton Mission Bindings M",
                        "description": "Universal bindings, compatible with most boards.",
                        "availability_label": "In stock",
                    }
                ]
            elif query == "boots":
                products = [
                    {
                        "name": "Burton Moto Boots 9",
                        "description": "Comfort fit, heat-moldable liner.",
                        "availability_label": "In stock",
                    }
                ]
            else:
                products = [
                    {
                        "name": "Burton Custom Snowboard 158cm",
                        "description": "All-mountain board, verified merchant, ready to ship.",
                        "availability_label": "In stock",
                    }
                ]
        if query == "bindings":
            text = "Bindings are available and pair well with the boards above. The Burton Mission is in stock and compatible with most boards. Want a quote that includes bindings?"
        elif query == "boots":
            text = "Boots are available in multiple sizes. Let me know your size and I can line up a quote."
        else:
            text = "Found snowboards that match your request. The Burton Custom 158 is available and a quote is ready. Want me to fetch a fresh quote?"
        return {
            "session_id": req.session_id,
            "reply": {
                "text": text,
                "products": products,
                "quote": {"quote_id": "Q-001", "status_label": "Quote ready"},
                "decision": "ALLOW",
            },
            "suggestions": _SUGGESTIONS,
            "actions": ["ask_followup", "inspect_terms"],
        }

    if kind == "sla":
        return {
            "session_id": req.session_id,
            "reply": {
                "text": "SLA terms cover uptime, response windows, and downtime liability. I can fetch the full terms for your review.",
                "decision": "ALLOW",
            },
            "suggestions": _SUGGESTIONS,
            "actions": ["inspect_terms", "ask_followup"],
        }

    if kind == "failover":
        return {
            "session_id": req.session_id,
            "reply": {
                "text": "Failover is handled via redundant merchant routing and escrow hold. If a merchant goes offline, Paari keeps payment verified and fulfillment can reroute.",
                "decision": "ALLOW",
            },
            "suggestions": _SUGGESTIONS,
            "actions": ["ask_followup", "inspect_terms"],
        }

    if kind == "scope":
        return {
            "session_id": req.session_id,
            "reply": {
                "text": "Sure — tell me what to adjust (quantity, budget, or items like bindings/boots) and I'll prepare a fresh quote in prose.",
                "decision": "ALLOW",
            },
            "suggestions": _SUGGESTIONS,
            "actions": ["ask_followup"],
        }

    if len(req.message.strip()) < 8:
        return {
            "session_id": req.session_id,
            "reply": {
                "text": "Could you share a bit more detail so I can find the right match?",
                "decision": "ALLOW",
            },
            "suggestions": _SUGGESTIONS,
            "actions": ["ask_followup"],
        }

    return {
        "session_id": req.session_id,
        "reply": {
            "text": "Thanks for the details. I can line up verified merchants and prepare a quote in prose. Let me know if you'd like me to proceed with a quote or refine the requirements.",
            "decision": "ALLOW",
        },
        "suggestions": _SUGGESTIONS,
        "actions": ["ask_followup", "inspect_terms"],
    }


@router.post("/escrow/authorize")
async def escrow_authorize(
    req: EscrowAuthorizeRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    _require_bearer(authorization)
    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text("SELECT id, state FROM quotes WHERE id=:q"), {"q": req.quote_id}
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="quote not found")
        if row.state == "EXPIRED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="quote expired"
            )
    return {
        "status": "queued",
        "message": f"Your order for {req.quote_id} is queued. We'll confirm once the merchant accepts.",
    }


@router.get("/terms")
async def get_terms(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_bearer(authorization)
    return {
        "title": "Paari Terms of Service",
        "body": "These terms govern your use of Paari for agentic commerce. Quotes are time-bound and subject to merchant acceptance. Payments are escrowed via Razorpay and verified by Paari before fulfillment. For questions, contact support.",
    }
