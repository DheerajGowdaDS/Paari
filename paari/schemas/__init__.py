"""Protocol surface package — versioned, strict Pydantic schemas."""

from __future__ import annotations

from paari.schemas.audit import AuditDecision, AuditEvent
from paari.schemas.capability import Capability, CapabilitySet
from paari.schemas.governance import GovernanceDocument, PlatformLimits
from paari.schemas.identity import AgentId, AgentType, JwtClaims, MerchantId
from paari.schemas.policy import (
    PolicyDecision,
    PolicyDocument,
    PolicyLayer,
    PolicyOp,
    PolicyRule,
)
from paari.schemas.runtime import AgentIntent, AgentResponse, RuntimeContext
from paari.schemas.tool import (
    RiskLevel,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResultStatus,
)
from paari.schemas.transaction import (
    CreateTransaction,
    PaymentRequest,
    PaymentState,
    PaymentVerification,
    QuoteState,
    TxState,
)

__all__ = [
    "AgentId",
    "AgentType",
    "MerchantId",
    "JwtClaims",
    "Capability",
    "CapabilitySet",
    "GovernanceDocument",
    "PlatformLimits",
    "PolicyDecision",
    "PolicyDocument",
    "PolicyLayer",
    "PolicyOp",
    "PolicyRule",
    "AgentIntent",
    "AgentResponse",
    "RuntimeContext",
    "RiskLevel",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "ToolResultStatus",
    "CreateTransaction",
    "PaymentRequest",
    "PaymentState",
    "PaymentVerification",
    "QuoteState",
    "TxState",
    "AuditDecision",
    "AuditEvent",
]
