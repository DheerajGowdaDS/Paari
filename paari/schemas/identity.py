"""Identity and capability schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AgentType(str, Enum):
    BUYER = "BUYER"
    MERCHANT = "MERCHANT"
    SYSTEM = "SYSTEM"


class MerchantId(BaseModel):
    """Strict merchant identifier."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique merchant identifier (UUID).")


class AgentId(BaseModel):
    """Strict agent identifier."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique agent identifier (UUID).")
    agent_type: AgentType = Field(..., description="BUYER | MERCHANT | SYSTEM")


class JwtClaims(BaseModel):
    """The exact shape of a Paari-issued RS256 agent JWT."""

    model_config = ConfigDict(extra="forbid")

    sub: str = Field(..., description="agent_id")
    agent_type: AgentType
    merchant_scope: str | None = Field(default=None, description="merchant_id or null")
    capabilities: list[str] = Field(default_factory=list)
    policy_version: str
    iat: int = Field(..., description="issued at (unix seconds)")
    exp: int = Field(..., description="expiry (unix seconds)")
    jti: str = Field(..., description="unique token id for revocation")
    iss: str = Field(default="paari-platform")
