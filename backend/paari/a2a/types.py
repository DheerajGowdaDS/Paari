"""A2A message types for agent-to-agent communication in Paari."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class A2AAction(str, Enum):
    DISCOVER = "DISCOVER"
    REQUEST_QUOTE = "REQUEST_QUOTE"
    ACCEPT_QUOTE = "ACCEPT_QUOTE"
    EXECUTE_PAYMENT = "EXECUTE_PAYMENT"
    PAYMENT_RESULT = "PAYMENT_RESULT"
    FULFILL_ORDER = "FULFILL_ORDER"
    CANCEL = "CANCEL"
    NEGOTIATE = "NEGOTIATE"
    COUNTER_OFFER = "COUNTER_OFFER"


class A2AStatus(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DENIED = "DENIED"
    PENDING = "PENDING"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"


class A2AMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique message ID for idempotency",
    )
    sender_id: str = Field(..., description="Agent ID of sender")
    receiver_id: str = Field(..., description="Agent ID of receiver")
    action: A2AAction = Field(..., description="A2A action type")
    payload: dict[str, Any] = Field(default_factory=dict, description="Action-specific payload")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Message timestamp",
    )
    auth_token: str | None = Field(default=None, description="JWT for authentication")
    idempotency_key: str | None = Field(
        default=None,
        description="Protection against duplicate requests",
    )
    reply_to: str | None = Field(
        default=None,
        description="message_id this is a reply to",
    )


class A2AResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(..., description="Echo request message_id")
    sender_id: str = Field(..., description="Responding agent")
    receiver_id: str = Field(..., description="Original sender")
    status: A2AStatus = Field(..., description="Response status")
    payload: dict[str, Any] = Field(default_factory=dict, description="Response data")
    error: str | None = Field(default=None, description="Error message if status is ERROR")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Response timestamp",
    )


class AgentRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="BUYER | MERCHANT | SYSTEM")
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of capability names",
    )
    merchant_id: str | None = Field(
        default=None,
        description="Associated merchant ID for merchant agents",
    )
    a2a_endpoint: str | None = Field(
        default=None,
        description="URL this agent listens on for A2A messages",
    )
    display_id: str | None = Field(
        default=None,
        description="Human-readable agent ID (e.g. BA-001)",
    )
    owner_id: str | None = Field(
        default=None,
        description="Owner user ID",
    )
    status: str = Field(default="ACTIVE", description="ACTIVE | INACTIVE | SUSPENDED")


class AgentCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    display_id: str | None = None
    agent_type: str
    capabilities: list[str] = Field(default_factory=list)
    merchant_id: str | None = None
    a2a_endpoint: str | None = None
    status: str = "ACTIVE"
    registered_at: datetime | None = None


class QuoteRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str | None = Field(default=None, description="Product SKU or ID")
    product_name: str | None = Field(default=None, description="Product name for search")
    quantity: int = Field(default=1, ge=1, description="Quantity")
    buyer_agent_id: str = Field(..., description="Requesting buyer agent")
    max_price_paise: int | None = Field(
        default=None,
        description="Maximum price buyer is willing to pay",
    )


class QuotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_id: str
    transaction_id: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    quantity: int
    amount_paise: int
    currency: str = "INR"
    expires_at: str
    state: str = "PENDING"
    merchant_agent_id: str
    buyer_agent_id: str
    line_items: list[dict] = Field(default_factory=list)


class AcceptQuotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_id: str
    buyer_agent_id: str
    transaction_id: str | None = Field(default=None, description="Optional pre-created transaction")


class PaymentExecutionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_session_id: str
    transaction_id: str
    razorpay_order_id: str | None = Field(
        default=None,
        description="Razorpay order ID if already created",
    )
    amount_paise: int
    currency: str = "INR"


class PaymentResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    payment_session_id: str
    razorpay_payment_id: str | None = None
    razorpay_order_id: str | None = None
    status: str = Field(..., description="VERIFIED | FAILED | PENDING")
    amount_paise: int
    currency: str = "INR"
    error_message: str | None = None


class FulfillOrderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    order_id: str | None = Field(default=None, description="Shopify order ID if created")
    fulfillment_status: str = Field(default="PENDING")
    tracking_number: str | None = None
    carrier: str | None = None


class NegotiatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_id: str
    counter_amount_paise: int
    message: str | None = None
    buyer_agent_id: str


class DiscoverPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(
        default=None,
        description="Search query for merchant discovery",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="Filter by required capabilities",
    )
    merchant_id: str | None = Field(
        default=None,
        description="Filter by specific merchant",
    )
