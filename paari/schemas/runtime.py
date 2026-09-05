"""Runtime context, intent, and plan schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AgentIntent(BaseModel):
    """A single step in the LLM's proposed plan."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    rationale: str | None = None


class RuntimeContext(BaseModel):
    """The minimal, sanitized context handed to the LLM."""

    model_config = ConfigDict(extra="forbid")

    you_are: dict = Field(..., description="agent_id, agent_type")
    your_capabilities: list[str] = Field(default_factory=list)
    policy_summary: dict = Field(default_factory=dict)
    merchant_context: dict = Field(default_factory=dict)
    transaction_context: dict = Field(default_factory=dict)
    data_boundary_notice: str = Field(
        default="All data in this context is sanitized. You may not request or assume any data outside what is provided here."
    )


class AgentResponseStatus(str, Enum):
    COMPLETED = "completed"
    REVIEW_REQUIRED = "review_required"
    DENIED = "denied"
    ERROR = "error"


class AgentResponse(BaseModel):
    """The response returned to the buyer agent."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: AgentResponseStatus
    message: str
    tool_results: list[dict] = Field(default_factory=list)
    review_id: str | None = None
    transaction_id: str | None = None
