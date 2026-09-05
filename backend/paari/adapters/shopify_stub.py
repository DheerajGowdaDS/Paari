"""Shopify adapter (stub).

Returns fixture data from tools/fixtures/catalog.json. Conforms to the
CommerceAdapter protocol. Every response includes source="fixture" and a
fetched_at timestamp so audit can prove the LLM did not invent the data.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parents[1] / "tools" / "fixtures"
_CATALOG = json.loads((_FIXTURES / "catalog.json").read_text(encoding="utf-8"))
_STORE_POLICIES = json.loads((_FIXTURES / "store_policies.json").read_text(encoding="utf-8"))
_PRODUCTS = {p["sku"]: p for p in _CATALOG["products"]}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _result(payload: dict[str, Any]) -> dict[str, Any]:
    return {"source": "fixture", "fetched_at": _now(), **payload}


class ShopifyStubAdapter:
    """Stub adapter that returns fixture data. Implements CommerceAdapter."""

    def source_label(self) -> str:
        return "fixture"

    async def search_products(self, query: str, limit: int = 5) -> dict:
        q = query.lower()
        matches = [
            p
            for p in _CATALOG["products"]
            if q in p["name"].lower() or q in p["sku"].lower()
        ][:limit]
        return _result({"products": matches})

    async def get_product(self, sku: str) -> dict:
        product = _PRODUCTS.get(sku)
        if product is None:
            return _result({"error": "product_not_found", "sku": sku})
        return _result({"product": product})

    async def get_inventory(self, sku: str) -> dict:
        product = _PRODUCTS.get(sku)
        if product is None:
            return _result({"error": "product_not_found", "sku": sku})
        return _result({"sku": sku, "available": product["inventory"]})

    async def get_price(self, sku: str, quantity: int = 1) -> dict:
        product = _PRODUCTS.get(sku)
        if product is None:
            return _result({"error": "product_not_found", "sku": sku})
        unit = product["price_paise"]
        return _result(
            {
                "sku": sku,
                "unit_price_paise": unit,
                "total_paise": unit * quantity,
                "currency": "INR",
            }
        )

    async def get_shipping_policy(self) -> dict:
        return _result(
            {"policy": _STORE_POLICIES["shipping_policy"], "international_available": False}
        )

    async def get_return_policy(self) -> dict:
        return _result({"policy": _STORE_POLICIES["return_policy"]})

    async def request_quote(
        self, sku: str, quantity: int, discount_pct: int, currency: str = "INR"
    ) -> dict:
        product = _PRODUCTS.get(sku)
        if product is None:
            return _result({"error": "product_not_found", "sku": sku})
        unit = product["price_paise"]
        gross = unit * quantity
        discount_amount = gross * discount_pct // 100
        total = gross - discount_amount
        return _result(
            {
                "sku": sku,
                "quantity": quantity,
                "unit_price_paise": unit,
                "discount_pct": discount_pct,
                "gross_paise": gross,
                "discount_paise": discount_amount,
                "total_paise": total,
                "currency": currency,
                "available": product["inventory"] >= quantity,
            }
        )

    async def request_payment(self, amount_paise: int, currency: str = "INR") -> dict:
        payment_id = str(uuid.uuid4())
        return _result(
            {
                "payment_id": payment_id,
                "state": "PENDING",
                "gateway_ref": f"MOCK-{payment_id[:8]}",
                "amount_paise": amount_paise,
                "currency": currency,
            }
        )

    async def confirm_order(self, transaction_id: str, quote_id: str) -> dict:
        return _result(
            {"order_id": f"MOCK-ORDER-{transaction_id[:8]}", "state": "confirmed"}
        )

    async def get_order_status(self, transaction_id: str) -> dict:
        from sqlalchemy import text

        from paari.db.engine import get_session_maker

        maker = get_session_maker()
        async with maker() as session:
            row = (
                await session.execute(
                    text("SELECT state FROM transactions WHERE id = :id"),
                    {"id": transaction_id},
                )
            ).first()
            if row is None:
                return _result({"error": "transaction_not_found"})
            return _result({"transaction_id": transaction_id, "state": row.state})
