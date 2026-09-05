"""Tool registry: every tool Paari exposes to an agent.

Each tool is metadata + a typed input schema + an executor. The registry is
the protocol surface: the LLM receives only the tools whose required
capability the agent holds.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from paari.schemas.capability import Capability
from paari.schemas.tool import RiskLevel, ToolDefinition
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

Executor = Callable[[BaseModel, str], Any]


@dataclass
class Tool:
    """A registered tool: metadata + typed input schema + executor."""

    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: dict[str, Any]
    required_capability: Capability
    risk_level: RiskLevel
    allowed_systems: set[str]
    executor: Executor

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema.model_json_schema(),
            output_schema=self.output_schema,
            required_capability=self.required_capability.value,
            risk_level=self.risk_level,
            allowed_systems=self.allowed_systems,
        )


def _json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    return schema


class ToolRegistry:
    """Holds every registered tool. Lookup is by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name}")
        return tool

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def tools_for(self, capabilities: list[str]) -> list[Tool]:
        """Return only tools whose required capability the agent holds."""
        cap_set = set(capabilities)
        return [t for t in self._tools.values() if t.required_capability.value in cap_set]

    def as_tool_definitions(self, capabilities: list[str] | None = None) -> list[ToolDefinition]:
        tools = self.tools_for(capabilities) if capabilities is not None else list(self._tools.values())
        return [t.definition for t in tools]

    def to_openai_tools(self, capabilities: list[str] | None = None) -> list[dict[str, Any]]:
        """Convert to OpenAI chat/completions tool format."""
        out: list[dict[str, Any]] = []
        for definition in self.as_tool_definitions(capabilities):
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": definition.name,
                        "description": definition.description,
                        "parameters": definition.input_schema,
                        "strict": True,
                    },
                }
            )
        return out


def _get_executors() -> dict[str, Callable]:
    """Get the executor functions based on PAARI_SHOPIFY_MODE."""
    from paari.config import settings

    if settings.shopify_mode == "live":
        # Live mode: wrap async adapter methods as sync executors
        from paari.adapters.shopify_live import ShopifyLiveAdapter

        adapter = ShopifyLiveAdapter()

        def _run_async(coro):
            import asyncio
            import concurrent.futures

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(coro)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(asyncio.run, coro).result()

        def search_products(inp, mid):
            return _run_async(adapter.search_products(inp.query, inp.limit))

        def get_product(inp, mid):
            return _run_async(adapter.get_product(inp.sku))

        def get_inventory(inp, mid):
            return _run_async(adapter.get_inventory(inp.sku))

        def get_price(inp, mid):
            return _run_async(adapter.get_price(inp.sku, inp.quantity))

        def get_shipping_policy(inp, mid):
            return _run_async(adapter.get_shipping_policy())

        def get_return_policy(inp, mid):
            return _run_async(adapter.get_return_policy())

        def request_quote(inp, mid):
            return _run_async(adapter.request_quote(inp.sku, inp.quantity, inp.discount_pct, inp.currency))

        def request_payment(inp, mid):
            return _run_async(adapter.request_payment(inp.amount_paise, inp.currency))

        def confirm_order(inp, mid):
            return _run_async(adapter.confirm_order(inp.transaction_id, inp.quote_id))

        def get_order_status(inp, mid):
            return _run_async(adapter.get_order_status(inp.transaction_id))

    else:
        # Stub mode: use existing sync executors
        from paari.tools.adapters.shopify_stub import (
            confirm_order,
            get_inventory,
            get_order_status,
            get_price,
            get_product,
            get_return_policy,
            get_shipping_policy,
            request_payment,
            request_quote,
            search_products,
        )

    return {
        "search_products": search_products,
        "get_product": get_product,
        "get_inventory": get_inventory,
        "get_price": get_price,
        "get_shipping_policy": get_shipping_policy,
        "get_return_policy": get_return_policy,
        "request_quote": request_quote,
        "request_payment": request_payment,
        "confirm_order": confirm_order,
        "get_order_status": get_order_status,
    }


def build_registry() -> ToolRegistry:
    """Register every demo tool with its stub executor."""
    executors = _get_executors()

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="search_products",
            description="Search the merchant's product catalog by free-text query.",
            input_schema=SearchProductsInput,
            output_schema={"type": "object", "properties": {"products": {"type": "array"}}},
            required_capability=Capability.CATALOG_READ,
            risk_level=RiskLevel.LOW,
            allowed_systems={"SHOPIFY"},
            executor=executors["search_products"],
        )
    )
    registry.register(
        Tool(
            name="get_product",
            description="Look up a single product by SKU.",
            input_schema=GetProductInput,
            output_schema={"type": "object", "properties": {"product": {"type": "object"}}},
            required_capability=Capability.PRODUCT_READ,
            risk_level=RiskLevel.LOW,
            allowed_systems={"SHOPIFY"},
            executor=executors["get_product"],
        )
    )
    registry.register(
        Tool(
            name="get_inventory",
            description="Get current inventory for a product SKU.",
            input_schema=GetInventoryInput,
            output_schema={"type": "object", "properties": {"available": {"type": "integer"}}},
            required_capability=Capability.INVENTORY_READ,
            risk_level=RiskLevel.LOW,
            allowed_systems={"SHOPIFY"},
            executor=executors["get_inventory"],
        )
    )
    registry.register(
        Tool(
            name="get_price",
            description="Get the current price for a product SKU.",
            input_schema=GetPriceInput,
            output_schema={"type": "object", "properties": {"price_paise": {"type": "integer"}}},
            required_capability=Capability.CATALOG_READ,
            risk_level=RiskLevel.LOW,
            allowed_systems={"SHOPIFY"},
            executor=executors["get_price"],
        )
    )
    registry.register(
        Tool(
            name="get_shipping_policy",
            description="Get the merchant's shipping policy.",
            input_schema=GetShippingPolicyInput,
            output_schema={"type": "object", "properties": {"policy": {"type": "string"}}},
            required_capability=Capability.CATALOG_READ,
            risk_level=RiskLevel.LOW,
            allowed_systems={"SHOPIFY"},
            executor=executors["get_shipping_policy"],
        )
    )
    registry.register(
        Tool(
            name="get_return_policy",
            description="Get the merchant's return policy.",
            input_schema=GetReturnPolicyInput,
            output_schema={"type": "object", "properties": {"policy": {"type": "string"}}},
            required_capability=Capability.CATALOG_READ,
            risk_level=RiskLevel.LOW,
            allowed_systems={"SHOPIFY"},
            executor=executors["get_return_policy"],
        )
    )
    registry.register(
        Tool(
            name="request_quote",
            description="Request a price quote for a product.",
            input_schema=RequestQuoteInput,
            output_schema={"type": "object", "properties": {"quote_id": {"type": "string"}}},
            required_capability=Capability.QUOTE_CREATE,
            risk_level=RiskLevel.MEDIUM,
            allowed_systems={"PAARI"},
            executor=executors["request_quote"],
        )
    )
    registry.register(
        Tool(
            name="request_payment",
            description="Request payment for an authorized quote.",
            input_schema=RequestPaymentInput,
            output_schema={"type": "object", "properties": {"payment_id": {"type": "string"}}},
            required_capability=Capability.PAYMENT_REQUEST,
            risk_level=RiskLevel.HIGH,
            allowed_systems={"RAZORPAY"},
            executor=executors["request_payment"],
        )
    )
    registry.register(
        Tool(
            name="confirm_order",
            description="Confirm a Shopify order after payment is verified.",
            input_schema=ConfirmOrderInput,
            output_schema={"type": "object", "properties": {"order_id": {"type": "string"}}},
            required_capability=Capability.ORDER_READ,
            risk_level=RiskLevel.HIGH,
            allowed_systems={"SHOPIFY"},
            executor=executors["confirm_order"],
        )
    )
    registry.register(
        Tool(
            name="get_order_status",
            description="Get the status of a transaction's order.",
            input_schema=GetOrderStatusInput,
            output_schema={"type": "object", "properties": {"state": {"type": "string"}}},
            required_capability=Capability.ORDER_READ,
            risk_level=RiskLevel.MEDIUM,
            allowed_systems={"SHOPIFY"},
            executor=executors["get_order_status"],
        )
    )
    return registry


# Module-level singleton.
REGISTRY: ToolRegistry = build_registry()


def reload_registry() -> ToolRegistry:
    global REGISTRY
    REGISTRY = build_registry()
    return REGISTRY
