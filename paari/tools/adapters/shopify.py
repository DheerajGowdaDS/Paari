"""Shopify tool executor bridge.

Thin wrapper that delegates all calls to the configured CommerceAdapter
(via PAARI_SHOPIFY_MODE). The tool registry imports these functions as
executors. Signature: (input_model, merchant_id) -> dict.
"""

from __future__ import annotations

from typing import Any

from paari.adapters.commerce import get_commerce_adapter
from paari.schemas.tool_inputs import (
    ConfirmOrderInput,
    GetInventoryInput,
    GetOrderStatusInput,
    GetPriceInput,
    GetProductInput,
    GetReturnPolicyInput,
    GetShippingPolicyInput,
    RequestPaymentInput,
    RequestQuoteInput,
    SearchProductsInput,
)

# Lazy singleton adapter
_adapter = None


def _get_adapter():
    global _adapter
    if _adapter is None:
        _adapter = get_commerce_adapter()
    return _adapter


def search_products(input: SearchProductsInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().search_products(input.query, input.limit)
    )


def get_product(input: GetProductInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().get_product(input.sku)
    )


def get_inventory(input: GetInventoryInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().get_inventory(input.sku)
    )


def get_price(input: GetPriceInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().get_price(input.sku, input.quantity)
    )


def get_shipping_policy(input: GetShippingPolicyInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().get_shipping_policy()
    )


def get_return_policy(input: GetReturnPolicyInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().get_return_policy()
    )


def request_quote(input: RequestQuoteInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().request_quote(input.sku, input.quantity, input.discount_pct, input.currency)
    )


def request_payment(input: RequestPaymentInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().request_payment(input.amount_paise, input.currency)
    )


def confirm_order(input: ConfirmOrderInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().confirm_order(input.transaction_id, input.quote_id)
    )


def get_order_status(input: GetOrderStatusInput, merchant_id: str) -> dict[str, Any]:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _get_adapter().get_order_status(input.transaction_id)
    )
