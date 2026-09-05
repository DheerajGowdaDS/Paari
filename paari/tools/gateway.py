"""Tool execution gateway: the ONLY path from LLM intent to tool execution.

Pipeline (sequential, no skip path):
    1. Parse arguments against the tool's typed schema (rejects unknown fields)
    2. Capability check (AuthZ)
    3. Policy evaluation (deterministic ALLOW/REVIEW/DENY)
    4. Risk evaluation (probabilistic; HIGH forces REVIEW)
    5. Execute the tool via its adapter
    6. Audit the outcome (synchronously, before response)

There is no flag, no conditional, no code path that bypasses a step. The
only way to skip a step is to modify the gateway source (a deployment-time
concern), not a runtime concern an LLM can manipulate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from paari.audit.logger import AuditLogger
from paari.authn.jwt_verifier import Identity
from paari.authz.engine import AuthorizationEngine
from paari.policy_engine.engine import PolicyContext, PolicyEngine
from paari.risk.engine import RiskEngine
from paari.schemas.audit import AuditDecision
from paari.schemas.tool import ToolResult, ToolResultStatus
from paari.tools.registry import REGISTRY, ToolRegistry

_log = logging.getLogger("paari.gateway")


@dataclass
class GatewayContext:
    """The context the gateway evaluates for one tool call."""

    identity: Identity
    merchant_id: str
    request_id: str
    transaction_id: str | None = None
    quote_id: str | None = None
    tx_context: dict[str, Any] = field(default_factory=dict)
    merchant_context: dict[str, Any] = field(default_factory=dict)


class GatewayError(Exception):
    """Raised when the gateway cannot proceed (e.g. unknown tool)."""


class ToolGateway:
    """Executes a tool call through the full enforcement pipeline."""

    def __init__(
        self,
        registry: ToolRegistry,
        authz: AuthorizationEngine,
        policy: PolicyEngine,
        risk: RiskEngine,
        audit: AuditLogger,
    ) -> None:
        self._registry = registry
        self._authz = authz
        self._policy = policy
        self._risk = risk
        self._audit = audit

    async def execute(self, ctx: GatewayContext, tool_name: str, raw_arguments: dict[str, Any]) -> ToolResult:
        """Run the full pipeline for one tool call. Returns a ToolResult."""
        request_id = ctx.request_id

        # 1. Look up the tool and parse arguments against its typed schema.
        try:
            tool = self._registry.get(tool_name)
        except KeyError:
            await self._audit.log(request_id=request_id, action=tool_name, decision=AuditDecision.FAILED, agent_id=ctx.identity.agent_id, merchant_id=ctx.merchant_id, payload={"reason": "unknown_tool"})
            return ToolResult(call_id="", tool_name=tool_name, status=ToolResultStatus.ERROR, reason="unknown_tool")

        try:
            validated = tool.input_schema.model_validate(raw_arguments)
        except ValidationError as exc:
            # Structural non-bypass: unknown fields are rejected here.
            await self._audit.log(
                request_id=request_id,
                action=tool_name,
                decision=AuditDecision.FAILED,
                agent_id=ctx.identity.agent_id,
                merchant_id=ctx.merchant_id,
                payload={"reason": "tool_arg_rejected", "errors": exc.errors()},
            )
            return ToolResult(
                call_id="",
                tool_name=tool_name,
                status=ToolResultStatus.ERROR,
                reason="tool_arg_rejected",
                payload={"errors": exc.errors()},
            )

        # 2. Capability check (AuthZ). The JWT carries the agent's granted
        # capabilities (expanded to their transitive closure at issuance time),
        # so checking the identity's claims is the authoritative runtime check.
        required = tool.required_capability.value
        if required not in ctx.identity.capabilities:
            await self._audit.log(
                request_id=request_id,
                action=tool_name,
                decision=AuditDecision.DENY,
                agent_id=ctx.identity.agent_id,
                merchant_id=ctx.merchant_id,
                payload={"reason": "missing_capability", "required": required, "granted": ctx.identity.capabilities},
            )
            return ToolResult(call_id="", tool_name=tool_name, status=ToolResultStatus.DENIED, reason="missing_capability")

        # 3. Policy evaluation (deterministic ALLOW/REVIEW/DENY).
        policy_ctx = PolicyContext(
            tx={**ctx.tx_context, "amount_paise": ctx.tx_context.get("amount_paise")},
            agent={"agent_id": ctx.identity.agent_id, "agent_type": ctx.identity.agent_type.value},
            merchant=ctx.merchant_context,
            store={"international": False},
        )
        policy_decision = self._policy.evaluate(policy_ctx)
        if policy_decision.decision == "DENY":
            await self._audit.log(
                request_id=request_id,
                action=tool_name,
                decision=AuditDecision.DENY,
                agent_id=ctx.identity.agent_id,
                merchant_id=ctx.merchant_id,
                policy_version=policy_decision.policy_version,
                payload={"reason": policy_decision.reason, "rules": policy_decision.contributing_rules},
            )
            return ToolResult(call_id="", tool_name=tool_name, status=ToolResultStatus.DENIED, reason=policy_decision.reason)
        if policy_decision.decision == "REVIEW":
            await self._audit.log(
                request_id=request_id,
                action=tool_name,
                decision=AuditDecision.REVIEW,
                agent_id=ctx.identity.agent_id,
                merchant_id=ctx.merchant_id,
                policy_version=policy_decision.policy_version,
                payload={"reason": policy_decision.reason, "rules": policy_decision.contributing_rules},
            )
            return ToolResult(call_id="", tool_name=tool_name, status=ToolResultStatus.REVIEW_REQUIRED, reason=policy_decision.reason)

        # 4. Risk evaluation (probabilistic; HIGH forces REVIEW).
        risk_score = self._risk.evaluate({"tx": ctx.tx_context, "merchant": ctx.merchant_context, "agent": {"agent_id": ctx.identity.agent_id}})
        if risk_score.level.value == "HIGH":
            await self._audit.log(
                request_id=request_id,
                action=tool_name,
                decision=AuditDecision.REVIEW,
                agent_id=ctx.identity.agent_id,
                merchant_id=ctx.merchant_id,
                risk_score=risk_score.score,
                payload={"reason": "risk_high", "triggered_rules": risk_score.triggered_rules},
            )
            return ToolResult(call_id="", tool_name=tool_name, status=ToolResultStatus.REVIEW_REQUIRED, reason=f"risk_score:{risk_score.score}")

        # 5. Execute the tool via its adapter.
        try:
            payload = tool.executor(validated, ctx.merchant_id)
        except Exception as exc:  # noqa: BLE001 - adapter failure is a gateway failure
            _log.exception("tool executor failed: %s", tool_name)
            await self._audit.log(
                request_id=request_id,
                action=tool_name,
                decision=AuditDecision.FAILED,
                agent_id=ctx.identity.agent_id,
                merchant_id=ctx.merchant_id,
                payload={"reason": "executor_error", "error": str(exc)},
            )
            return ToolResult(call_id="", tool_name=tool_name, status=ToolResultStatus.ERROR, reason="executor_error")

        # 6. Audit the successful execution (synchronously, before response).
        await self._audit.log(
            request_id=request_id,
            action=tool_name,
            decision=AuditDecision.EXECUTED,
            agent_id=ctx.identity.agent_id,
            merchant_id=ctx.merchant_id,
            risk_score=risk_score.score,
            payload={"result": payload},
        )

        return ToolResult(call_id="", tool_name=tool_name, status=ToolResultStatus.OK, payload=payload)


# Module-level singleton.
GATEWAY = ToolGateway(
    registry=REGISTRY,
    authz=__import__("paari.authz", fromlist=["AUTHZ"]).AUTHZ,
    policy=__import__("paari.policy_engine.engine", fromlist=["PolicyEngine"]).PolicyEngine.for_merchant(),
    risk=__import__("paari.risk", fromlist=["RISK_ENGINE"]).RISK_ENGINE,
    audit=__import__("paari.audit.logger", fromlist=["AuditLogger"]).AuditLogger(),
)


def get_gateway() -> ToolGateway:
    return GATEWAY
