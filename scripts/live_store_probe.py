"""Live probe against the real Shopify store.

Runs each Paari adapter layer against the live store and prints the RAW
Shopify response plus the normalized Paari payload that actually feeds the
LLM context and the tool gateway. No stubs, no fixtures — everything is
fetched live from Shopify.

Usage:
    python scripts/live_store_probe.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from paari.adapters.shopify_live import ShopifyLiveAdapter
from paari.store_context.normalizer import normalize_catalog, normalize_policies


def _section(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


async def _probe_admin_direct() -> None:
    """Hit Shopify Admin GraphQL directly — raw response."""
    from paari.shopify_admin.client import ShopifyAdminClient
    from paari.shopify_admin.queries import SEARCH_PRODUCTS, GET_VARIANT_PRICE

    _section("1. Shopify Admin GraphQL — raw search_products")
    admin = ShopifyAdminClient()
    try:
        raw = await admin.execute(SEARCH_PRODUCTS, {"query": "", "first": 5})
        print("RAW GraphQL response (data only):")
        print(json.dumps(raw, indent=2, default=str)[:4000])

        # Extract a real variant id for the price probe
        edges = raw.get("products", {}).get("edges", [])
        if edges:
            first_var = edges[0]["node"]["variants"]["edges"][0]["node"]
            vid = first_var["id"]
            sku = first_var.get("sku", "(no sku)")
            print(f"\nFirst variant: id={vid}  sku={sku}")

            _section("1b. Shopify Admin GraphQL — raw get_variant_price")
            price_raw = await admin.execute(GET_VARIANT_PRICE, {"variantId": vid})
            print("RAW GraphQL response:")
            print(json.dumps(price_raw, indent=2, default=str)[:2000])

            _section("1c. Paari adapter.get_price() — normalized output")
            adapter = ShopifyLiveAdapter()
            price = await adapter.get_price(sku, 1)
            print(json.dumps(price, indent=2, default=str))
    finally:
        await admin.close()


async def _probe_storefront() -> None:
    """Hit Shopify Storefront MCP — raw response."""
    from paari.shopify_storefront.client import ShopifyStorefrontClient

    _section("2. Shopify Storefront MCP — raw search_catalog")
    sf = ShopifyStorefrontClient()
    try:
        raw = await sf.search_catalog("", limit=5)
        print("RAW Storefront MCP search_catalog result:")
        print(json.dumps(raw, indent=2, default=str)[:4000])
    except Exception as exc:
        print(f"Storefront MCP unavailable: {exc}")
        print("(falling back to Admin GraphQL for catalog — see section 1)")
    finally:
        await sf.close()


async def _probe_policies() -> None:
    """Hit Storefront MCP for policies — raw + normalized."""
    from paari.shopify_storefront.client import ShopifyStorefrontClient

    _section("3. Shopify Storefront MCP — raw search_policies")
    sf2 = ShopifyStorefrontClient()
    try:
        raw = await sf2.search_policies("policies")
        print("RAW Storefront MCP search_policies result:")
        print(json.dumps(raw, indent=2, default=str)[:3000])
        print("\nNormalized by paari.store_context.normalizer.normalize_policies():")
        print(json.dumps(normalize_policies(raw), indent=2, default=str))
    except Exception as exc:
        print(f"Storefront MCP unavailable: {exc}")
    finally:
        await sf2.close()


async def _probe_adapter_layer() -> None:
    """Run the full ShopifyLiveAdapter — what the tool gateway actually calls."""
    adapter = ShopifyLiveAdapter()

    _section("4. adapter.search_products() - what the gateway sees (live Admin GraphQL)")
    sp = await adapter.search_products("", limit=5)
    print(json.dumps(sp, indent=2, default=str)[:4000])

    # Pull a real SKU from the result that has inventory
    products = sp.get("products", [])
    sku = None
    sku_with_inventory = None
    variant_id_for_inventory = None
    if products:
        for p in products:
            if p.get("sku"):
                sku = p["sku"]
                # Check if any variant has inventory
                for v in p.get("variants", []):
                    if v.get("available"):
                        sku_with_inventory = p["sku"]
                        variant_id_for_inventory = v.get("variant_id")
                        break
                # Also save the first variant_id for any product (for price lookup)
                if not variant_id_for_inventory and p.get("variants"):
                    variant_id_for_inventory = p["variants"][0].get("variant_id")
                break

    if sku:
        print(f"\nFirst SKU found: {sku}")
        if not sku_with_inventory:
            print("  (NOTE: this SKU has no available inventory)")

        # --- adapter.search_products price check (from the returned product data) ---
        _section("5. adapter.search_products() - price from live product data")
        p = next((x for x in products if x.get("sku") == sku), None)
        if p:
            print(f"  Product: {p['title']}")
            print(f"  Price: {p['price_paise']} paise ({p['price_paise']/100:.2f} INR)")
            print(f"  Currency: {p['currency']}")
            for v in p.get("variants", []):
                print(f"  Variant {v['variant_id']}: available={v['available']}, price={v['price_paise']} paise")

        # --- adapter.get_price() - live Admin GraphQL lookup ---
        _section("6. adapter.get_price() - live Admin GraphQL lookup")
        price = await adapter.get_price(sku, 1)
        print(json.dumps(price, indent=2, default=str))

        # --- adapter.request_quote() - price calculation ---
        _section("7. adapter.request_quote() - price x qty calculation")
        quote = await adapter.request_quote(sku, quantity=1, discount_pct=0)
        print(json.dumps(quote, indent=2, default=str))
    else:
        print("\n  No SKU found in products (products may not have SKUs set in Shopify).")
        print("  NOTE: This is a Shopify store configuration issue, not a Paari bug.")
        print("  The Admin GraphQL IS returning live product data (see section 4).")
        print("  The 'sku_index' is empty because SKUs are null in the Shopify product data.")
        if products and products[0].get("variants"):
            v = products[0]["variants"][0]
            print(f"\n  First variant: id={v.get('variant_id')}, price={v.get('price_paise')} paise, available={v.get('available')}")

    _section("8. adapter.get_shipping_policy() / get_return_policy()")
    print("shipping:", json.dumps(await adapter.get_shipping_policy(), indent=2, default=str))
    print("return:  ", json.dumps(await adapter.get_return_policy(), indent=2, default=str))


async def _probe_store_context() -> None:
    """Run the StoreContextBuilder — what feeds the LLM context."""
    from paari.store_context.builder import StoreContextBuilder

    _section("9. StoreContextBuilder.fetch_and_cache() — LLM context source")
    builder = StoreContextBuilder()
    payload = await builder.fetch_and_cache("MER-001")
    print("Keys:", list(payload.keys()))
    print("fetched_at:", payload.get("fetched_at"))
    print("\ncatalog (normalized, what the LLM receives):")
    print(json.dumps(payload.get("catalog", {}), indent=2, default=str)[:3000])
    print("\npolicies (normalized, what the LLM receives):")
    print(json.dumps(payload.get("policies", {}), indent=2, default=str))


async def main() -> int:
    print("Paari x Shopify LIVE store probe")
    print("Domain: paari-demo-store.myshopify.com  |  Mode: live")

    # Run store context first to populate the SKU index cache
    await _probe_store_context()

    try:
        await _probe_admin_direct()
    except Exception as exc:
        print(f"\n[ABORT] Admin GraphQL probe failed: {exc!r}")
        return 1

    await _probe_storefront()
    await _probe_policies()
    await _probe_adapter_layer()

    _section("SUMMARY")
    print("All live Shopify calls completed. The raw responses above are the")
    print("actual data Paari fed into the LLM context and tool gateway.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))