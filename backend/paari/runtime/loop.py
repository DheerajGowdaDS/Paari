"""The Paari Agent Runtime: the canonical loop connecting LLM + governance + tools.

Loop:
    USER / BUYER AGENT
        ↓
      LLM (with sanitized context + approved tools)
        ↓
    Intent / Plan
        ↓
    For each step:
        Capability Check (AuthZ)
        ↓
        Policy Check (deterministic ALLOW/REVIEW/DENY)
        ↓
        Risk Check (probabilistic; HIGH forces REVIEW)
        ↓
        Tool Execution (through the gateway)
        ↓
        Tool Result
        ↓
        LLM (next action)
        ↓
    Response
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from paari.audit.logger import AUDIT, AuditLogger
from paari.authn.jwt_verifier import Identity
from paari.llm.client import LLM, LLMClient, LLMError
from paari.llm.constitution import PAARI_CONSTITUTION
from paari.llm.context_builder import CONTEXT_BUILDER, ContextBuilder
from paari.llm.tools_schema import to_openai_tools
from paari.memory.runtime_state import new_id
from paari.runtime.planner import Planner
from paari.runtime.step_executor import StepExecutor
from paari.schemas.audit import AuditDecision
from paari.schemas.runtime import AgentResponse, AgentResponseStatus
from paari.schemas.tool import ToolResultStatus
from paari.tools.gateway import GATEWAY, GatewayContext, ToolGateway

_log = logging.getLogger("paari.runtime")


@dataclass
class RuntimeLoop:
    """Drives one buyer request through the full Paari pipeline."""

    llm: LLMClient
    context_builder: ContextBuilder
    gateway: ToolGateway
    executor: StepExecutor
    audit: AuditLogger
    planner: Planner = field(default_factory=Planner)
    max_steps: int = 6

    async def _persist_transaction(self, request_id: str, identity: Identity, merchant_id: str, tx_context: dict[str, Any]) -> str:
        """INSERT a transactions row at loop start. Returns transaction_id."""
        from sqlalchemy import text

        from paari.db.engine import get_session_maker

        transaction_id = new_id()
        amount = tx_context.get("amount_paise") or 0
        maker = get_session_maker()
        async with maker() as session:
            await session.execute(
                text(
                    "INSERT INTO transactions (id, merchant_id, buyer_agent_id, amount_paise, currency, state, policy_version) "
                    "VALUES (:id, :mid, :bid, :amount, :cur, :state, :pv)"
                ),
                {
                    "id": transaction_id,
                    "mid": merchant_id,
                    "bid": identity.agent_id,
                    "amount": amount,
                    "cur": tx_context.get("currency", "INR"),
                    "state": "REQUESTED",
                    "pv": identity.policy_version,
                },
            )
            await session.commit()
        return transaction_id

    async def _update_transaction_state(self, transaction_id: str, state: str) -> None:
        """Update a transaction's state in the DB."""
        from sqlalchemy import text

        from paari.db.engine import get_session_maker

        maker = get_session_maker()
        async with maker() as session:
            await session.execute(
                text("UPDATE transactions SET state = :state, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                {"id": transaction_id, "state": state},
            )
            await session.commit()

    async def _create_review(self, merchant_id: str, transaction_id: str, step: Any, ctx: GatewayContext, reason: str) -> str:
        """Create a review row for a REVIEW_REQUIRED result. Returns review_id."""
        from paari.review.service import REVIEW

        pending_step = {"tool_name": step.tool_name, "arguments": step.arguments}
        gw_ctx = {
            "identity": {
                "agent_id": ctx.identity.agent_id,
                "agent_type": ctx.identity.agent_type.value,
                "capabilities": ctx.identity.capabilities,
                "policy_version": ctx.identity.policy_version,
            },
            "merchant_id": ctx.merchant_id,
            "tx_context": ctx.tx_context,
            "merchant_context": ctx.merchant_context,
        }
        record = await REVIEW.create(
            merchant_id=merchant_id,
            transaction_id=transaction_id,
            triggered_by="POLICY",
            reason=reason,
            pending_step=pending_step,
            gateway_context=gw_ctx,
        )
        return record.id

    async def run(self, identity: Identity, buyer_request: str, **tx_overrides: Any) -> AgentResponse:
        """Run the full loop for one buyer request."""
        request_id = new_id()
        tx_context = {
            "amount_paise": tx_overrides.get("amount_paise"),
            "currency": tx_overrides.get("currency", "INR"),
            "quantity": tx_overrides.get("quantity", 1),
            "discount_pct": tx_overrides.get("discount_pct", 0),
            "sku": tx_overrides.get("sku"),
            "international": False,
            "hour_utc": tx_overrides.get("hour_utc", 12),
            "count_per_minute": tx_overrides.get("count_per_minute", 1),
            "seconds_since_last": tx_overrides.get("seconds_since_last", 600),
        }
        merchant_id = self.context_builder.merchant_id
        ctx = GatewayContext(
            identity=identity,
            merchant_id=merchant_id,
            request_id=request_id,
            tx_context=tx_context,
            merchant_context={
                "average_transaction_paise": self.context_builder.average_transaction_paise,
                "autonomous_limit_paise": self.context_builder.autonomous_limit_paise,
                "active_hours_utc": self.context_builder.active_hours_utc,
            },
        )

        # Persist the transaction at loop start (Phase 9: "use your database").
        transaction_id = await self._persist_transaction(request_id, identity, merchant_id, tx_context)
        ctx.transaction_id = transaction_id

        # 1. Build the sanitized runtime context and expose only approved tools.
        runtime_context = self.context_builder.build(identity, tx_context)
        tools = to_openai_tools(self.gateway._registry, identity.capabilities)

        # 2. Ask the LLM for a plan.
        try:
            llm_response = await self.llm.complete(
                constitution=PAARI_CONSTITUTION,
                context=runtime_context.model_dump(),
                tools=tools,
                user_input=buyer_request,
            )
        except LLMError as exc:
            await self.audit.log(
                request_id=request_id,
                action="agent.run",
                decision=AuditDecision.FAILED,
                agent_id=identity.agent_id,
                merchant_id=ctx.merchant_id,
                payload={"reason": str(exc)},
            )
            return AgentResponse(
                request_id=request_id,
                status=AgentResponseStatus.ERROR,
                message=f"LLM unavailable: {exc}",
            )

        steps = self.planner.parse(llm_response)
        if not steps:
            # No tool calls: the LLM answered in prose. Return that.
            await self.audit.log(
                request_id=request_id,
                action="agent.run",
                decision=AuditDecision.EXECUTED,
                agent_id=identity.agent_id,
                merchant_id=ctx.merchant_id,
                payload={"content": llm_response.content},
            )
            return AgentResponse(
                request_id=request_id,
                status=AgentResponseStatus.COMPLETED,
                message=llm_response.content or "No action proposed.",
            )

        # 3. Execute each step through the gateway.
        tool_results: list[dict[str, Any]] = []
        for step in steps[: self.max_steps]:
            result = await self.executor.execute(ctx, step)
            tool_results.append(result.model_dump())
            if result.status == ToolResultStatus.DENIED:
                await self._update_transaction_state(transaction_id, "DENIED")
                await self.audit.log(
                    request_id=request_id,
                    action=step.tool_name,
                    decision=AuditDecision.DENY,
                    agent_id=identity.agent_id,
                    merchant_id=ctx.merchant_id,
                    payload={"reason": result.reason},
                )
                return AgentResponse(
                    request_id=request_id,
                    status=AgentResponseStatus.DENIED,
                    message=f"Action denied by Paari policy: {result.reason}",
                    tool_results=tool_results,
                    transaction_id=transaction_id,
                )
            if result.status == ToolResultStatus.REVIEW_REQUIRED:
                # Create a review row so the merchant dashboard can act on it.
                review_id = await self._create_review(ctx.merchant_id, transaction_id, step, ctx, result.reason)
                await self._update_transaction_state(transaction_id, "REVIEW_REQUIRED")
                await self.audit.log(
                    request_id=request_id,
                    action=step.tool_name,
                    decision=AuditDecision.REVIEW,
                    agent_id=identity.agent_id,
                    merchant_id=ctx.merchant_id,
                    payload={"reason": result.reason, "review_id": review_id},
                )
                return AgentResponse(
                    request_id=request_id,
                    status=AgentResponseStatus.REVIEW_REQUIRED,
                    message=f"Merchant review required: {result.reason}",
                    tool_results=tool_results,
                    review_id=review_id,
                    transaction_id=transaction_id,
                )
            if result.status == ToolResultStatus.ERROR:
                return AgentResponse(
                    request_id=request_id,
                    status=AgentResponseStatus.ERROR,
                    message=f"Tool error: {result.reason}",
                    tool_results=tool_results,
                )

        # 4. Summarize for the buyer.
        await self._update_transaction_state(transaction_id, "COMPLETED")
        await self.audit.log(
            request_id=request_id,
            action="agent.run",
            decision=AuditDecision.EXECUTED,
            agent_id=identity.agent_id,
            merchant_id=ctx.merchant_id,
            payload={"steps": len(tool_results)},
        )
        return AgentResponse(
            request_id=request_id,
            status=AgentResponseStatus.COMPLETED,
            message=f"Completed {len(tool_results)} tool call(s).",
            tool_results=tool_results,
            transaction_id=transaction_id,
        )


# Module-level singleton.
RUNTIME = RuntimeLoop(
    llm=LLM,
    context_builder=CONTEXT_BUILDER,
    gateway=GATEWAY,
    executor=StepExecutor(GATEWAY),
    audit=AUDIT,
)


def get_runtime() -> RuntimeLoop:
    return RUNTIME
