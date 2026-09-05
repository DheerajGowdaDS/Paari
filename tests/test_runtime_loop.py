"""Step 13 validation: the agent runtime loop."""

from __future__ import annotations

import json

import httpx
import respx

from paari.authn.jwt_verifier import Identity
from paari.llm.client import LLMClient
from paari.llm.context_builder import CONTEXT_BUILDER
from paari.runtime.loop import RuntimeLoop
from paari.runtime.planner import Planner
from paari.runtime.step_executor import StepExecutor
from paari.schemas.identity import AgentType
from paari.schemas.runtime import AgentResponseStatus
from paari.tools.gateway import GATEWAY


def _identity() -> Identity:
    return Identity(
        agent_id="buyer-agent-001",
        agent_type=AgentType.BUYER,
        merchant_scope=None,
        capabilities=["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"],
        policy_version="v1",
        jti="t1",
    )


def _loop(llm: LLMClient) -> RuntimeLoop:
    return RuntimeLoop(
        llm=llm,
        context_builder=CONTEXT_BUILDER,
        gateway=GATEWAY,
        executor=StepExecutor(GATEWAY),
        audit=__import__("paari.audit.logger", fromlist=["AuditLogger"]).AuditLogger(),
        planner=Planner(),
    )


@respx.mock
async def test_loop_executes_proposed_tool_call() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Looking that up.",
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
    llm = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m")
    loop = _loop(llm)
    response = await loop.run(_identity(), "find SKU-001")
    assert response.status == AgentResponseStatus.COMPLETED
    assert len(response.tool_results) == 1
    assert response.tool_results[0]["tool_name"] == "get_product"
    assert response.tool_results[0]["payload"]["product"]["sku"] == "SKU-001"


@respx.mock
async def test_loop_policy_deny_returns_denied() -> None:
    """A 20% discount is denied by merchant policy M-02."""
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "request_quote",
                                        "arguments": json.dumps({"sku": "SKU-001", "quantity": 1, "discount_pct": 20, "currency": "INR"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )
    )
    llm = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m")
    loop = _loop(llm)
    response = await loop.run(_identity(), "buy SKU-001 with 20% off", discount_pct=20)
    assert response.status == AgentResponseStatus.DENIED
    assert "policy" in response.message.lower() or "deny" in response.message.lower()


@respx.mock
async def test_loop_policy_review_returns_review_required() -> None:
    """₹25,000 exceeds the merchant autonomous limit -> REVIEW."""
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "request_quote",
                                        "arguments": json.dumps({"sku": "SKU-001", "quantity": 1, "discount_pct": 0, "currency": "INR"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )
    )
    llm = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m")
    loop = _loop(llm)
    response = await loop.run(_identity(), "buy SKU-001", amount_paise=2500000)
    assert response.status == AgentResponseStatus.REVIEW_REQUIRED


@respx.mock
async def test_loop_llm_unavailable_returns_error() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(side_effect=httpx.ConnectError("refused"))
    llm = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m", timeout_s=0.1)
    loop = _loop(llm)
    response = await loop.run(_identity(), "buy SKU-001")
    assert response.status == AgentResponseStatus.ERROR


@respx.mock
async def test_loop_no_tool_calls_returns_completed() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "I cannot help with that.", "tool_calls": []}}]},
        )
    )
    llm = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m")
    loop = _loop(llm)
    response = await loop.run(_identity(), "anything")
    assert response.status == AgentResponseStatus.COMPLETED
    assert response.message == "I cannot help with that."


@respx.mock
async def test_loop_unknown_tool_dropped() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {"name": "bypass_everything", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            },
        )
    )
    llm = LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m")
    loop = _loop(llm)
    response = await loop.run(_identity(), "do something bad")
    # Unknown tool -> gateway returns ERROR -> runtime reports error.
    assert response.status == AgentResponseStatus.ERROR
