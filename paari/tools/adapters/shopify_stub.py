"""Shopify adapter (stub).

Returns fixture data from tools/fixtures/catalog.json. The adapter interface
is the integration point for a real Shopify connection later. Every response
includes source="fixture" and a fetched_at timestamp so audit can prove the
LLM did not invent the data.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paari.schemas.tool_inputs import (
    ConfirmOrderInput,
    GetInventoryInput,
    GetOrderStatusInput,
    GetPriceInput,
    GetProductInput,
    GetReturnPolicyInput,
    GetShippingPolicyInput,
    RequestQuoteInput,
    SearchProductsInput,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_CATALOG = json.loads((_FIXTURES / "catalog.json").read_text(encoding="utf-8"))
_STORE_POLICIES = json.loads((_FIXTURES / "store_policies.json").read_text(encoding="utf-8"))
_PRODUCTS = {p["sku"]: p for p in _CATALOG["products"]}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _result(payload: dict[str, Any]) -> dict[str, Any]:
    return {"source": "fixture", "fetched_at": _now(), **payload}


def search_products(input: SearchProductsInput, merchant_id: str) -> dict[str, Any]:
    query = input.query.lower()
    matches = [
        p for p in _CATALOG["products"]
        if query in p["name"].lower() or query in p["sku"].lower()
    ][: input.limit]
    return _result({"products": matches})


def get_product(input: GetProductInput, merchant_id: str) -> dict[str, Any]:
    product = _PRODUCTS.get(input.sku)
    if product is None:
        return _result({"error": "product_not_found", "sku": input.sku})
    return _result({"product": product})


def get_inventory(input: GetInventoryInput, merchant_id: str) -> dict[str, Any]:
    product = _PRODUCTS.get(input.sku)
    if product is None:
        return _result({"error": "product_not_found", "sku": input.sku})
    return _result({"sku": input.sku, "available": product["inventory"], "source": "fixture"})


def get_price(input: GetPriceInput, merchant_id: str) -> dict[str, Any]:
    product = _PRODUCTS.get(input.sku)
    if product is None:
        return _result({"error": "product_not_found", "sku": input.sku})
    unit = product["price_paise"]
    return _result({"sku": input.sku, "unit_price_paise": unit, "total_paise": unit * input.quantity, "currency": "INR"})


def get_shipping_policy(input: GetShippingPolicyInput, merchant_id: str) -> dict[str, Any]:
    return _result({"policy": _STORE_POLICIES["shipping_policy"], "international_available": False})


def get_return_policy(input: GetReturnPolicyInput, merchant_id: str) -> dict[str, Any]:
    return _result({"policy": _STORE_POLICIES["return_policy"]})


def request_quote(input: RequestQuoteInput, merchant_id: str) -> dict[str, Any]:
    """Create a quote. The quote is recorded in the DB by the gateway; here we
    return the quote payload for the gateway to persist."""
    product = _PRODUCTS.get(input.sku)
    if product is None:
        return _result({"error": "product_not_found", "sku": input.sku})
    unit = product["price_paise"]
    gross = unit * input.quantity
    discount_amount = gross * input.discount_pct // 100
    total = gross - discount_amount
    return _result(
        {
            "sku": input.sku,
            "quantity": input.quantity,
            "unit_price_paise": unit,
            "discount_pct": input.discount_pct,
            "gross_paise": gross,
            "discount_paise": discount_amount,
            "total_paise": total,
            "currency": input.currency,
            "available": product["inventory"] >= input.quantity,
        }
    )


def request_payment(input, merchant_id: str) -> dict[str, Any]:
    """Request payment. Returns a PENDING response with a payment id.

    The gateway persists the payment row and blocks on the webhook for
    VERIFIED. This stub only generates the payment id and state.
    """
    payment_id = str(uuid.uuid4())
    return _result(
        {
            "payment_id": payment_id,
            "state": "PENDING",
            "gateway_ref": f"MOCK-{payment_id[:8]}",
            "amount_paise": input.amount_paise,
            "currency": input.currency,
        }
    )


def confirm_order(input: ConfirmOrderInput, merchant_id: str) -> dict[str, Any]:
    """Confirm a Shopify order (stub). Returns a synthetic order id."""
    return _result({"order_id": f"MOCK-ORDER-{input.transaction_id[:8]}", "state": "confirmed"})


def _run_async(coro):
    """Run a coroutine to completion from sync code, even inside a running loop."""
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


def get_order_status(input: GetOrderStatusInput, merchant_id: str) -> dict[str, Any]:
    """Return the transaction's order state from the DB."""
    return _run_async(_get_order_status_async(input.transaction_id))


async def _get_order_status_async(transaction_id: str) -> dict[str, Any]:
    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        row = (await session.execute(text("SELECT state FROM transactions WHERE id = :id"), {"id": transaction_id})).first()
        if row is None:
            return _result({"error": "transaction_not_found"})
        return _result({"transaction_id": transaction_id, "state": row.state})
