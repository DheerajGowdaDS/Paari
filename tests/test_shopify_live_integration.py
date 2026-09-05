"""Integration test for live Shopify adapter with mocked API responses.

Tests the full live adapter flow against simulated Shopify Admin + Storefront
responses, verifying the adapter correctly transforms Shopify data into
Paari's internal format.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Mock Shopify API responses ──────────────────────────────────────

MOCK_SHOP_QUERY_RESPONSE = {
    "data": {"shop": {"name": "Paari Demo Store", "id": "gid://shopify/Shop/123"}}
}

MOCK_PRODUCTS_RESPONSE = {
    "data": {
        "products": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/Product/8849231044900",
                        "title": "Nike Runner 9 - Black",
                        "description": "Lightweight running shoe",
                        "productType": "Footwear",
                        "tags": ["running", "nike"],
                        "variants": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "gid://shopify/ProductVariant/45231044923100",
                                        "sku": "NIKE-RUNNER-9-BLK",
                                        "price": "8499.00",
                                        "inventoryQuantity": 15,
                                    }
                                }
                            ]
                        },
                    }
                },
                {
                    "node": {
                        "id": "gid://shopify/Product/8849231044901",
                        "title": "Nike Runner 9 - White",
                        "description": "Lightweight running shoe",
                        "productType": "Footwear",
                        "tags": ["running", "nike"],
                        "variants": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "gid://shopify/ProductVariant/45231044923101",
                                        "sku": "NIKE-RUNNER-9-WHT",
                                        "price": "8499.00",
                                        "inventoryQuantity": 8,
                                    }
                                }
                            ]
                        },
                    }
                },
            ]
        }
    }
}

MOCK_INVENTORY_RESPONSE = {
    "data": {
        "productVariant": {
            "id": "gid://shopify/ProductVariant/45231044923199",
            "inventoryItem": {
                "id": "gid://shopify/InventoryItem/49231044923100",
                "inventoryLevels": {
                    "edges": [
                        {
                            "node": {
                                "quantities": [{"name": "available", "quantity": 15}],
                                "location": {"name": "Main Warehouse", "isActive": True},
                            }
                        }
                    ]
                },
            },
        }
    }
}

MOCK_VARIANT_PRICE_RESPONSE = {
    "data": {
        "productVariant": {
            "id": "gid://shopify/ProductVariant/45231044923100",
            "sku": "NIKE-RUNNER-9-BLK",
            "price": "8499.00",
            "compareAtPrice": None,
        }
    }
}

MOCK_DRAFT_ORDER_CREATE_RESPONSE = {
    "data": {
        "draftOrderCreate": {
            "draftOrder": {
                "id": "gid://shopify/DraftOrder/90001",
                "invoiceNumber": "1001",
                "status": "OPEN",
            },
            "userErrors": [],
        }
    }
}

MOCK_DRAFT_ORDER_COMPLETE_RESPONSE = {
    "data": {
        "draftOrderComplete": {
            "draftOrder": {
                "id": "gid://shopify/DraftOrder/90001",
                "order": {
                    "id": "gid://shopify/Order/90002",
                    "orderNumber": 1001,
                    "financialStatus": "PAID",
                    "fulfillmentStatus": "UNFULFILLED",
                },
            },
            "userErrors": [],
        }
    }
}

MOCK_WEBHOOK_CREATE_RESPONSE = {
    "data": {
        "webhookSubscriptionCreate": {
            "webhookSubscription": {
                "id": "gid://shopify/WebhookSubscription/50001",
                "topic": "ORDERS_CREATE",
                "callbackUrl": "https://example.ngrok-free.app/webhooks/shopify/orders_create",
            },
            "userErrors": [],
        }
    }
}


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_client_execute_query() -> None:
    """Test that ShopifyAdminClient executes GraphQL and parses response."""
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()

    # Mock the httpx client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SHOP_QUERY_RESPONSE
    mock_response.headers = {}

    mock_httpx = AsyncMock()
    mock_httpx.post.return_value = mock_response
    mock_httpx.is_closed = False

    with patch.object(client, "_get_client", return_value=mock_httpx):
        result = await client.execute("{ shop { name } }")
        assert result["shop"]["name"] == "Paari Demo Store"


@pytest.mark.asyncio
async def test_admin_client_rate_limit_retry() -> None:
    """Test 429 backoff and retry."""
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()

    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.headers = {"Retry-After": "1"}

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = MOCK_SHOP_QUERY_RESPONSE
    ok_response.headers = {}

    mock_httpx = AsyncMock()
    mock_httpx.post.side_effect = [rate_limited, ok_response]
    mock_httpx.is_closed = False

    with patch.object(client, "_get_client", return_value=mock_httpx):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.execute("{ shop { name } }")
            assert result["shop"]["name"] == "Paari Demo Store"
            assert mock_httpx.post.call_count == 2


@pytest.mark.asyncio
async def test_admin_client_auth_error() -> None:
    """Test 401 raises AuthError."""
    from paari.adapters.exceptions import AuthError
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.headers = {}

    mock_httpx = AsyncMock()
    mock_httpx.post.return_value = mock_response
    mock_httpx.is_closed = False

    with patch.object(client, "_get_client", return_value=mock_httpx):
        with pytest.raises(AuthError):
            await client.execute("{ shop { name } }")


@pytest.mark.asyncio
async def test_admin_get_inventory_quantity() -> None:
    """Test inventory query parsing."""
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_INVENTORY_RESPONSE
    mock_response.headers = {}

    mock_httpx = AsyncMock()
    mock_httpx.post.return_value = mock_response
    mock_httpx.is_closed = False

    with patch.object(client, "_get_client", return_value=mock_httpx):
        qty = await client.get_inventory_quantity("gid://shopify/ProductVariant/45231044923199")
        assert qty == 15


@pytest.mark.asyncio
async def test_admin_get_variant_price() -> None:
    """Test price query converts to paise."""
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_VARIANT_PRICE_RESPONSE
    mock_response.headers = {}

    mock_httpx = AsyncMock()
    mock_httpx.post.return_value = mock_response
    mock_httpx.is_closed = False

    with patch.object(client, "_get_client", return_value=mock_httpx):
        price = await client.get_variant_price("gid://shopify/ProductVariant/45231044923100")
        assert price == 849900  # 8499.00 * 100


@pytest.mark.asyncio
async def test_admin_create_draft_order() -> None:
    """Test draft order creation with paari_transaction note."""
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_DRAFT_ORDER_CREATE_RESPONSE
    mock_response.headers = {}

    mock_httpx = AsyncMock()
    mock_httpx.post.return_value = mock_response
    mock_httpx.is_closed = False

    with patch.object(client, "_get_client", return_value=mock_httpx):
        draft_id = await client.create_draft_order(
            line_items=[{"variantId": "gid://shopify/ProductVariant/45231044923100", "quantity": 2}],
            note="paari_transaction:tx-abc-123",
            tags=["paari-agent-order"],
        )
        assert draft_id == "gid://shopify/DraftOrder/90001"


@pytest.mark.asyncio
async def test_admin_complete_draft_order() -> None:
    """Test draft order completion returns order ID."""
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_DRAFT_ORDER_COMPLETE_RESPONSE
    mock_response.headers = {}

    mock_httpx = AsyncMock()
    mock_httpx.post.return_value = mock_response
    mock_httpx.is_closed = False

    with patch.object(client, "_get_client", return_value=mock_httpx):
        order_id = await client.complete_draft_order("gid://shopify/DraftOrder/90001")
        assert order_id == "gid://shopify/Order/90002"


@pytest.mark.asyncio
async def test_admin_create_webhook_subscription() -> None:
    """Test webhook subscription creation."""
    from paari.shopify_admin.client import ShopifyAdminClient

    client = ShopifyAdminClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_WEBHOOK_CREATE_RESPONSE
    mock_response.headers = {}

    mock_httpx = AsyncMock()
    mock_httpx.post.return_value = mock_response
    mock_httpx.is_closed = False

    with patch.object(client, "_get_client", return_value=mock_httpx):
        webhook_id = await client.create_webhook_subscription(
            "orders/create", "https://example.ngrok-free.app/webhooks/shopify/orders_create"
        )
        assert webhook_id == "gid://shopify/WebhookSubscription/50001"


@pytest.mark.asyncio
async def test_normalizer_products_from_shopify() -> None:
    """Test that normalizer converts Shopify product edges to Paari format."""
    from paari.store_context.normalizer import normalize_catalog, normalize_product

    shopify_products = [edge["node"] for edge in MOCK_PRODUCTS_RESPONSE["data"]["products"]["edges"]]

    # Test single product
    p = normalize_product(shopify_products[0])
    assert p["sku"] == "NIKE-RUNNER-9-BLK"
    assert p["title"] == "Nike Runner 9 - Black"
    assert p["price_paise"] == 849900
    assert p["product_type"] == "Footwear"
    assert "running" in p["tags"]
    assert len(p["variants"]) == 1
    assert p["variants"][0]["variant_id"] == "gid://shopify/ProductVariant/45231044923100"

    # Test catalog normalization with SKU index
    catalog = normalize_catalog(shopify_products)
    assert catalog["product_count"] == 2
    assert "NIKE-RUNNER-9-BLK" in catalog["sku_index"]
    assert "NIKE-RUNNER-9-WHT" in catalog["sku_index"]
    assert catalog["sku_index"]["NIKE-RUNNER-9-BLK"]["price"] == 849900
    assert catalog["sku_index"]["NIKE-RUNNER-9-BLK"]["product_id"] == "gid://shopify/Product/8849231044900"


@pytest.mark.asyncio
async def test_live_adapter_search_products() -> None:
    """Test live adapter search_products via mocked storefront client."""
    from paari.adapters.shopify_live import ShopifyLiveAdapter

    adapter = ShopifyLiveAdapter()

    mock_client = AsyncMock()
    mock_client.search_catalog.return_value = [
        {
            "sku": "NIKE-RUNNER-9-BLK",
            "title": "Nike Runner 9 - Black",
            "price_paise": 849900,
        }
    ]

    with patch.object(adapter, "_get_storefront_client", return_value=mock_client):
        result = await adapter.search_products("nike", 5)
        assert result["source"] == "shopify_live"
        assert len(result["products"]) == 1
        assert result["products"][0]["sku"] == "NIKE-RUNNER-9-BLK"
        mock_client.search_catalog.assert_called_once_with("nike", 5)


@pytest.mark.asyncio
async def test_live_adapter_confirm_order_flow() -> None:
    """Test the full draft order create -> complete flow."""
    from paari.adapters.shopify_live import ShopifyLiveAdapter

    adapter = ShopifyLiveAdapter()

    mock_admin = AsyncMock()
    mock_admin.create_draft_order.return_value = "gid://shopify/DraftOrder/90001"
    mock_admin.complete_draft_order.return_value = "gid://shopify/Order/90002"

    with patch.object(adapter, "_get_admin_client", return_value=mock_admin):
        result = await adapter.confirm_order("tx-abc-123", "q-456")
        assert result["source"] == "shopify_live"
        assert result["state"] == "confirmed"
        assert result["order_id"] == "gid://shopify/Order/90002"

        # Verify the note contains paari_transaction:tx-abc-123
        call_args = mock_admin.create_draft_order.call_args
        assert "paari_transaction:tx-abc-123" in call_args.kwargs["note"]
        assert "paari-agent-order" in call_args.kwargs["tags"]


@pytest.mark.asyncio
async def test_live_adapter_confirm_order_uses_quoted_sku() -> None:
    """G1: confirm_order emits one line item for the quoted SKU, not the whole index."""
    from pathlib import Path
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from paari.adapters.shopify_live import ShopifyLiveAdapter
    from paari.db import engine as db_engine

    db_path = Path(__file__).resolve().parent / f"_test_g1_{uuid4().hex}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        # Fresh schema (includes the product_sku / quantity columns)
        sql = (Path(__file__).resolve().parent.parent / "paari" / "db" / "init.sql").read_text(
            encoding="utf-8"
        )
        cleaned = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
        async with engine.begin() as conn:
            for stmt in (p.strip() for p in cleaned.split(";") if p.strip()):
                await conn.exec_driver_sql(stmt)

        tx_id, quote_id = str(uuid4()), str(uuid4())
        async with maker() as session:
            await session.execute(
                text(
                    "INSERT INTO transactions (id, display_id, merchant_id, buyer_agent_id, "
                    "amount_paise, currency, state, policy_version) "
                    "VALUES (:id, 'TXN-G1', 'MER-001', 'BA-001', 94995, 'INR', "
                    "'PAYMENT_VERIFIED', 'v1')"
                ),
                {"id": tx_id},
            )
            await session.execute(
                text(
                    "INSERT INTO quotes (id, transaction_id, merchant_id, product_sku, "
                    "quantity, amount_paise, expires_at, state) "
                    "VALUES (:id, :tid, 'MER-001', 'SNOW-900-BLK', 2, 189990, "
                    ":exp, 'ACCEPTED')"
                ),
                {"id": quote_id, "tid": tx_id, "exp": "2099-01-01T00:00:00+00:00"},
            )
            await session.commit()

        adapter = ShopifyLiveAdapter()
        mock_admin = AsyncMock()
        mock_admin.create_draft_order.return_value = "gid://shopify/DraftOrder/90001"
        mock_admin.complete_draft_order.return_value = "gid://shopify/Order/90002"

        async def _fake_index() -> dict:
            return {
                "SNOW-900-BLK": {
                    "variant_id": "gid://shopify/ProductVariant/9001",
                    "price": 94995,
                },
                "SNOW-900-WHT": {
                    "variant_id": "gid://shopify/ProductVariant/9002",
                    "price": 94995,
                },
            }

        with (
            patch.object(adapter, "_load_sku_index", side_effect=_fake_index),
            patch.object(adapter, "_get_admin_client", return_value=mock_admin),
            patch.object(db_engine, "get_session_maker", return_value=maker),
        ):
            result = await adapter.confirm_order(tx_id, quote_id)

        assert result["state"] == "confirmed"
        assert result["line_items_count"] == 1
        line_items = mock_admin.create_draft_order.call_args.kwargs["line_items"]
        assert line_items == [{"variantId": "gid://shopify/ProductVariant/9001", "quantity": 2}]
    finally:
        await engine.dispose()
        db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_live_adapter_get_inventory_fallback() -> None:
    """Test live adapter falls back gracefully on storefront error."""
    from paari.adapters.shopify_live import ShopifyLiveAdapter
    from paari.adapters.exceptions import AdapterError

    adapter = ShopifyLiveAdapter()

    mock_client = AsyncMock()
    mock_client.search_catalog.side_effect = AdapterError("Connection failed")

    with patch.object(adapter, "_get_storefront_client", return_value=mock_client):
        result = await adapter.search_products("test", 5)
        assert result["source"] == "shopify_live"
        assert result["products"] == []  # graceful fallback


@pytest.mark.asyncio
async def test_webhook_handler_order_event() -> None:
    """Test webhook order handler updates transaction state."""
    from paari.webhooks.handlers import handle_order_event
    from paari.webhooks.queue import WebhookEvent

    # First create a transaction in the DB
    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    tx_id = "test-webhook-tx-001"
    async with maker() as session:
        # Insert a test transaction
        await session.execute(
            text(
                "INSERT OR IGNORE INTO transactions (id, merchant_id, buyer_agent_id, "
                "amount_paise, currency, state, policy_version) "
                "VALUES (:id, :mid, :bid, :amount, :cur, :state, :pv)"
            ),
            {
                "id": tx_id,
                "mid": "MER-001",
                "bid": "BA-001",
                "amount": 120000,
                "cur": "INR",
                "state": "PAYMENT_PENDING",
                "pv": "v1",
            },
        )
        await session.commit()

    event = WebhookEvent(
        event_id="evt-order-001",
        source="SHOPIFY",
        merchant_id="MER-001",
        topic="orders/create",
        webhook_id="wh-order-001",
        payload={
            "id": "shopify-order-123",
            "financial_status": "paid",
            "note": f"paari_transaction:{tx_id}",
            "tags": ["paari-agent-order"],
        },
    )

    await handle_order_event(event)

    # Verify the transaction was updated
    async with maker() as session:
        row = (
            await session.execute(
                text("SELECT state FROM transactions WHERE id = :id"), {"id": tx_id}
            )
        ).first()
        assert row is not None
        assert row.state == "ORDER_CONFIRMED"


def test_full_tool_registry_live_mode() -> None:
    """Verify registry builds correctly and tool executors work."""
    from paari.tools.registry import build_registry

    reg = build_registry()
    assert len(reg.names()) == 10

    # All expected tools present
    expected = {
        "search_products", "get_product", "get_inventory", "get_price",
        "get_shipping_policy", "get_return_policy", "request_quote",
        "request_payment", "confirm_order", "get_order_status",
    }
    assert expected == set(reg.names())
