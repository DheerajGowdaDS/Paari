"""Step 10 validation: LLM client, context builder, tools schema."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from paari.authn.jwt_verifier import Identity
from paari.llm.client import LLMClient, LLMError
from paari.llm.context_builder import CONTEXT_BUILDER
from paari.llm.tools_schema import to_openai_tools
from paari.schemas.identity import AgentType
from paari.tools.registry import REGISTRY


def _identity() -> Identity:
    return Identity(
        agent_id="buyer-agent-001",
        agent_type=AgentType.BUYER,
        merchant_scope=None,
        capabilities=["catalog.read", "payment.request"],
        policy_version="v1",
        jti="t1",
    )


def test_context_builder_sanitize_strips_secrets() -> None:
    """The context must not contain any credential-like fields."""
    ctx = CONTEXT_BUILDER.build(_identity(), {"buyer_request": "buy SKU-001", "amount_paise": 120000})
    serialized = ctx.model_dump_json()
    for banned in ("api_key", "secret", "token", "password", "credential"):
        assert banned not in serialized.lower(), f"context leaks '{banned}'"


def test_context_builder_has_policy_summary() -> None:
    ctx = CONTEXT_BUILDER.build(_identity(), {"buyer_request": "buy SKU-001", "amount_paise": 120000})
    assert ctx.policy_summary["autonomous_limit_paise"] == 2_000_000
    assert "full_policy_hash" in ctx.policy_summary
    assert ctx.policy_summary["policy_version"]


def test_context_builder_merchant_context_no_internal_ids() -> None:
    ctx = CONTEXT_BUILDER.build(_identity(), {"buyer_request": "buy SKU-001", "amount_paise": 120000})
    # Merchant context is sanitized: no raw DB ids, no payment tokens.
    assert "merchant_id" in ctx.merchant_context
    assert "api_key" not in json.dumps(ctx.merchant_context).lower()


def test_tools_schema_exposes_only_granted() -> None:
    tools = to_openai_tools(REGISTRY, ["catalog.read", "payment.request"])
    names = {t["function"]["name"] for t in tools}
    assert "request_payment" in names
    assert "search_products" in names
    assert "get_product" not in names  # needs product.read
    assert "confirm_order" not in names  # needs order.read


def test_tools_schema_strict() -> None:
    tools = to_openai_tools(REGISTRY, ["catalog.read"])
    for t in tools:
        assert t["function"].get("strict") is True
        assert "parameters" in t["function"]


@respx.mock
async def test_llm_client_posts_chat_completions() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "I'll look that up.",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {"name": "get_product", "arguments": json.dumps({"sku": "SKU-001"})},
                                }
                            ],
                        }
                    }
                ]
            },
        )
    )
    client = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="test-model")
    response = await client.complete(
        constitution="You are a test agent.",
        context={"you_are": {"agent_id": "a-1"}},
        tools=[{"type": "function", "function": {"name": "get_product"}}],
        user_input="find SKU-001",
    )
    assert response.content == "I'll look that up."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["tool_name"] == "get_product"
    assert response.tool_calls[0]["arguments"] == {"sku": "SKU-001"}


@respx.mock
async def test_llm_client_raises_on_http_error() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(return_value=httpx.Response(500, json={"error": "boom"}))
    client = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m")
    with pytest.raises(LLMError):
        await client.complete(constitution="x", context={}, tools=[], user_input="hi")


@respx.mock
async def test_llm_client_raises_on_timeout() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(side_effect=httpx.TimeoutException("timed out"))
    client = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m", timeout_s=0.1)
    with pytest.raises(LLMError):
        await client.complete(constitution="x", context={}, tools=[], user_input="hi")


@respx.mock
def test_llm_client_no_api_key_in_logs(caplog) -> None:
    """The API key must never appear in log output."""
    import logging

    respx.post("https://api.example.com/v1/chat/completions").mock(side_effect=httpx.ConnectError("conn refused"))
    client = LLMClient(base_url="https://api.example.com/v1", api_key="super-secret-key", model="m", timeout_s=0.1)
    with caplog.at_level(logging.WARNING):
        try:
            asyncio_run(client.complete(constitution="x", context={}, tools=[], user_input="hi"))
        except Exception:
            pass
    assert "super-secret-key" not in caplog.text


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
