"""Shopify Storefront MCP client.

Wraps the MCP Python client (mcp.ClientSession) over streamablehttp_client
to communicate with the Storefront MCP endpoint. Provides typed helpers
for catalog search, product lookup, and policy search.
"""

from __future__ import annotations

import logging
from typing import Any

from paari.adapters.exceptions import AdapterError, AuthError

_log = logging.getLogger("paari.shopify_storefront.client")


class ShopifyStorefrontClient:
    """MCP client wrapper for Shopify Storefront."""

    def __init__(self) -> None:
        from paari.config import settings

        self._url = settings.resolved_storefront_mcp_url()
        self._session: Any = None

    async def _get_session(self) -> Any:
        """Lazy-init the MCP session."""
        if self._session is not None:
            return self._session

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            read_stream, write_stream = await streamablehttp_client(self._url).__aenter__()
            self._session = await ClientSession(read_stream, write_stream).__aenter__()
            await self._session.initialize()
            return self._session
        except ImportError:
            raise AdapterError(
                "mcp package not installed. Install with: pip install mcp"
            )
        except Exception as e:
            raise AdapterError(f"Failed to connect to Storefront MCP: {e}")

    async def close(self) -> None:
        """Close the MCP session."""
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and return the result content."""
        session = await self._get_session()
        try:
            result = await session.call_tool(tool_name, arguments)
            # MCP returns a list of content blocks
            if result and hasattr(result, "content"):
                for block in result.content:
                    if hasattr(block, "text"):
                        import json

                        return json.loads(block.text)
            return result
        except Exception as e:
            raise AdapterError(f"MCP tool call '{tool_name}' failed: {e}")

    async def search_catalog(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search the product catalog via Storefront MCP."""
        result = await self._call_tool(
            "search_shop_catalog", {"query": query, "limit": limit}
        )
        if isinstance(result, dict):
            return result.get("products", result.get("results", []))
        if isinstance(result, list):
            return result
        return []

    async def get_product(self, sku: str) -> dict[str, Any] | None:
        """Get a single product by SKU via Storefront MCP."""
        result = await self._call_tool("get_product", {"sku": sku})
        if isinstance(result, dict) and result.get("error"):
            return None
        return result

    async def search_policies(self, query: str = "") -> dict[str, Any]:
        """Search for shop policies and FAQs via Storefront MCP."""
        result = await self._call_tool(
            "search_shop_policies_and_faqs", {"query": query or "policies"}
        )
        if isinstance(result, dict):
            return result
        return {}
