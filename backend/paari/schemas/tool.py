"""Tool registry, tool call, and tool result schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ToolDefinition(BaseModel):
    """Metadata for one registered tool. This is the protocol surface."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_schema: dict = Field(..., description="JSON schema for tool arguments")
    output_schema: dict = Field(..., description="JSON schema for tool output")
    required_capability: str
    risk_level: RiskLevel
    allowed_systems: set[str] = Field(default_factory=set)


class ToolCall(BaseModel):
    """A request from the LLM to invoke a tool. Strict: no extra fields."""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(..., description="UUID4 for correlation")
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultStatus(str, Enum):
    OK = "OK"
    DENIED = "DENIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ERROR = "ERROR"


class ToolResult(BaseModel):
    """The result of a tool execution through the gateway."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    status: ToolResultStatus
    payload: dict[str, Any] | None = None
    reason: str | None = None
    source: str | None = None  # e.g. "fixture", "shopify", "razorpay"
    fetched_at: str | None = None  # ISO-8601 UTC
