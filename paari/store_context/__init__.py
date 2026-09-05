"""Store context: fetch, cache, and normalize Shopify store data for LLM consumption."""

from __future__ import annotations

from paari.store_context.builder import StoreContextBuilder, get_store_context

__all__ = ["StoreContextBuilder", "get_store_context"]
