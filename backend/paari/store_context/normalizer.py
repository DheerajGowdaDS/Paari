"""Normalize Shopify catalog + policy objects into Paari's LLM-friendly shape.

Normalizer ensures the LLM receives:
- SKU-based product records (not Shopify GIDs)
- Consistent price_paise / currency fields
- Normalized shipping and return policy dicts
"""

from __future__ import annotations

from typing import Any


def normalize_product(shopify_product: dict[str, Any]) -> dict[str, Any]:
    """Convert a Shopify product node to Paari's normalized shape."""
    variants = []
    for edge in shopify_product.get("variants", {}).get("edges", []):
        node = edge.get("node", {})
        variants.append(
            {
                "variant_id": node.get("id", ""),
                "sku": node.get("sku", ""),
                "price_paise": _shopify_price_to_paise(node.get("price", "0.00")),
                "available": (node.get("inventoryQuantity", 0) or 0) > 0,
            }
        )

    primary_variant = variants[0] if variants else {}
    return {
        "sku": primary_variant.get("sku", shopify_product.get("id", "")),
        "product_id": shopify_product.get("id", ""),
        "title": shopify_product.get("title", ""),
        "description": shopify_product.get("description", ""),
        "product_type": shopify_product.get("productType", ""),
        "tags": shopify_product.get("tags", []),
        "price_paise": primary_variant.get("price_paise", 0),
        "currency": "INR",
        "variants": variants,
    }


def normalize_catalog(shopify_products: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize a list of Shopify products into a Paari catalog."""
    normalized = [normalize_product(p) for p in shopify_products]
    sku_index = {}
    for p in normalized:
        for v in p.get("variants", []):
            if v.get("sku"):
                sku_index[v["sku"]] = {
                    "product_id": p["product_id"],
                    "variant_id": v["variant_id"],
                    "title": p["title"],
                    "price": v["price_paise"],
                }
    return {
        "products": normalized,
        "sku_index": sku_index,
        "product_count": len(normalized),
    }


def normalize_policies(mcp_policies: dict[str, Any]) -> dict[str, Any]:
    """Normalize Storefront MCP policy response into Paari's expected shape.

    Returns:
        {
            "shipping": {"international": bool, "free_threshold_paise": int, "estimate_days": str},
            "returns": {"window_days": int, "conditions": str},
        }
    """
    shipping = mcp_policies.get("shipping", mcp_policies.get("shipping_policy", ""))
    returns = mcp_policies.get("returns", mcp_policies.get("return_policy", ""))

    # Parse shipping policy (best effort)
    international = False
    free_threshold = 0
    estimate = "5-7 business days"
    if isinstance(shipping, str):
        lower = shipping.lower()
        international = "international" in lower and "unavailable" not in lower
        if "free" in lower:
            free_threshold = 500000  # ₹5,000 default
    elif isinstance(shipping, dict):
        international = shipping.get("international", False)
        free_threshold = shipping.get("free_threshold_paise", 0)
        estimate = shipping.get("estimate_days", estimate)

    # Parse return policy (best effort)
    window_days = 30
    conditions = "Unworn items with original tags"
    if isinstance(returns, str):
        import re

        match = re.search(r"(\d+)", returns)
        if match:
            window_days = int(match.group(1))
        conditions = returns
    elif isinstance(returns, dict):
        window_days = returns.get("window_days", window_days)
        conditions = returns.get("conditions", conditions)

    return {
        "shipping": {
            "international": international,
            "free_threshold_paise": free_threshold,
            "estimate_days": estimate,
        },
        "returns": {
            "window_days": window_days,
            "conditions": conditions,
        },
    }


def _shopify_price_to_paise(price_str: str) -> int:
    """Convert a Shopify price string (e.g. '1200.00') to paise."""
    try:
        return int(float(price_str) * 100)
    except (ValueError, TypeError):
        return 0
