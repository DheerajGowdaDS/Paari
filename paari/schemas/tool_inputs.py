"""Pydantic input schemas for every registered tool.

Every tool's input is a strict Pydantic model with extra='forbid'. This is
the structural non-bypass defense: the LLM cannot pass a field (e.g.
bypass_policy) that is not declared in the schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchProductsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Free-text search query")
    limit: int = Field(default=10, ge=1, le=100)


class GetProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., description="Product SKU, e.g. SKU-001")


class GetInventoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., description="Product SKU")


class GetPriceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., description="Product SKU")
    quantity: int = Field(default=1, ge=1)


class GetShippingPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str | None = Field(default=None)


class GetReturnPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str | None = Field(default=None)


class RequestQuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., description="Product SKU")
    quantity: int = Field(default=1, ge=1)
    discount_pct: int = Field(default=0, ge=0, le=100)
    currency: Literal["INR"] = "INR"


class RequestPaymentInput(BaseModel):
    """The ONLY shape a payment tool call can have."""

    model_config = ConfigDict(extra="forbid")

    quote_id: str = Field(..., description="Validated quote ID")
    amount_paise: int = Field(..., gt=0, description="Amount in smallest currency unit")
    currency: Literal["INR"] = "INR"
    payment_method: Literal["razorpay"] = "razorpay"


class ConfirmOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(..., description="Transaction ID to confirm")
    quote_id: str = Field(..., description="Quote ID that was paid")


class GetOrderStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(..., description="Transaction ID")
