"""Policy document, rule, and decision schemas (Rego-translatable)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PolicyLayer(str, Enum):
    PAARI = "PAARI"
    MERCHANT = "MERCHANT"
    STORE = "STORE"
    TX = "TX"


class PolicyOp(str, Enum):
    """Operator vocabulary. This exact subset is Rego-translatable."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    AND = "and"
    OR = "or"
    NOT = "not"


class PolicyRule(BaseModel):
    """A single deterministic rule. When evaluates true, decision applies."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Rule id, e.g. M-01")
    when: dict = Field(..., description="Condition tree using PolicyOp vocabulary")
    decision: Literal["ALLOW", "REVIEW", "DENY"]
    reason: str


class PolicyDocument(BaseModel):
    """A versioned, layered policy document. Source of truth for both Python and Rego."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    layer: PolicyLayer
    version: str
    rules: list[PolicyRule] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    """The output of the policy engine."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["ALLOW", "REVIEW", "DENY"]
    reason: str
    policy_version: str
    layer: PolicyLayer
    contributing_rules: list[str] = Field(default_factory=list)
