"""Audit event schema (immutable shape, write-only from the application)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class AuditEvent(BaseModel):
    """One row in the append-only audit_events table."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., description="UUID4, correlates a request through all layers")
    merchant_id: str | None = None
    agent_id: str | None = None
    action: str = Field(..., description="Tool name or gateway event, e.g. request_payment")
    decision: AuditDecision
    policy_version: str | None = None
    risk_score: int | None = None
    payload: dict[str, Any] | None = None
    timestamp: str | None = None  # ISO-8601 UTC, set at write time
