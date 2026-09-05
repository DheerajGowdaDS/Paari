"""Transaction, quote, and payment schemas."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TxState(str, Enum):
    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    POLICY_APPROVED = "POLICY_APPROVED"
    QUOTE_CREATED = "QUOTE_CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_VERIFIED = "PAYMENT_VERIFIED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    COMPLETED = "COMPLETED"
    DENIED = "DENIED"


class QuoteState(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"


class PaymentState(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class CreateTransaction(BaseModel):
    """Request to start a transaction (buyer agent intent)."""

    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    buyer_request: str = Field(..., description="Natural-language buyer intent")
    amount_paise: int = Field(..., gt=0)
    currency: Literal["INR"] = "INR"
    quantity: int = Field(default=1, gt=0)
    discount_pct: int = Field(default=0, ge=0)
    sku: str | None = None


class PaymentRequest(BaseModel):
    """The ONLY shape a payment tool call can have. extra=forbid is the non-bypass defense."""

    model_config = ConfigDict(extra="forbid")

    quote_id: str
    amount_paise: int = Field(..., gt=0)
    currency: Literal["INR"] = "INR"
    payment_method: Literal["razorpay"] = "razorpay"


class PaymentVerification(BaseModel):
    """Verified payment event from the gateway/webhook (never from the agent)."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    gateway_ref: str
    amount_paise: int = Field(..., gt=0)
    currency: Literal["INR"] = "INR"
    signature: str = Field(..., description="HMAC signature over the event payload")
