"""Storefront MCP tools.

Typed wrappers for the Storefront MCP tools. These are called by
shopify_live.py but can also be used directly for testing.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from paari.adapters.exceptions import AdapterError

_log = logging.getLogger("paari.shopify_storefront.tools")


async def search_shop_catalog(
    session: Any, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    """Call the search_shop_catalog MCP tool."""
    try:
        result = await session.call_tool(
            "search_shop_catalog", {"query": query, "limit": limit}
        )
        if result and hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    if isinstance(data, dict):
                        return data.get("products", data.get("results", []))
                    if isinstance(data, list):
                        return data
        return []
    except Exception as e:
        _log.error("search_shop_catalog failed: %s", e)
        raise AdapterError(f"Catalog search failed: {e}")


async def get_product(session: Any, sku: str) -> dict[str, Any] | None:
    """Call the get_product MCP tool."""
    try:
        result = await session.call_tool("get_product", {"sku": sku})
        if result and hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    if isinstance(data, dict) and not data.get("error"):
                        return data
        return None
    except Exception as e:
        _log.error("get_product failed: %s", e)
        raise AdapterError(f"Product lookup failed: {e}")


async def search_shop_policies_and_faqs(session: Any, query: str = "") -> dict[str, Any]:
    """Call the search_shop_policies_and_faqs MCP tool."""
    try:
        result = await session.call_tool(
            "search_shop_policies_and_faqs", {"query": query or "policies"}
        )
        if result and hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    if isinstance(data, dict):
                        return data
        return {}
    except Exception as e:
        _log.error("search_shop_policies_and_faqs failed: %s", e)
        raise AdapterError(f"Policy search failed: {e}")
