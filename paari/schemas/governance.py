"""Governance document schema (the platform's non-negotiable rules).

Also carries the transaction-level governance evaluation schemas:
CheckResult, GovernanceDecision, GovernanceRequest.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from paari.schemas.policy import PolicyLayer


class PlatformLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_autonomous_transaction_paise: int
    payment_session_ttl_seconds: int
    max_payment_retries: int


class GovernanceDocument(BaseModel):
    """The full Paari platform governance document.

    This is distinct from PolicyDocument (the layered policy files). The
    governance document carries the constitution's MUST/MUST NOT lists and the
    P-01..P-10 mandatory rules; the layered PolicyDocument carries the
    deterministic rule tree the policy engine evaluates.
    """

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    layer: PolicyLayer = PolicyLayer.PAARI
    version: str
    must: list[str]
    must_not: list[str]
    mandatory_rules: dict[str, str]
    platform_limits: PlatformLimits
    rules: list[dict] = Field(default_factory=list)


# ── Transaction-level governance schemas ─────────────────────────────

CheckStatus = Literal["PASS", "FAIL", "REVIEW"]


class CheckResult(BaseModel):
    """Uniform result returned by every governance rule check."""

    model_config = ConfigDict(extra="forbid")

    check: str = Field(..., description="Rule identifier, e.g. AGENT_IDENTITY")
    status: CheckStatus = Field(..., description="PASS | FAIL | REVIEW")
    reason_code: str = Field(..., description="Machine-readable outcome, e.g. AGENT_NOT_FOUND")
    details: dict = Field(default_factory=dict, description="Arbitrary structured context")

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"

    @property
    def review(self) -> bool:
        return self.status == "REVIEW"


class GovernanceDecision(BaseModel):
    """Aggregated outcome of all governance checks."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    transaction_id: str
    transaction_display_id: str = ""
    decision: Literal["ALLOW", "REVIEW", "DENY"] = "DENY"
    checks: list[CheckResult] = Field(default_factory=list)
    policy_version: str = ""

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if c.failed]

    @property
    def review_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if c.review]


class GovernanceRequest(BaseModel):
    """Request body for POST /gateway/governance/evaluate."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(..., description="UUID or display_id of the transaction")
    request_id: str = Field(default="", description="Optional correlation id; generated if empty")
