"""Capability schema (least-privilege capability tokens)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Capability(str, Enum):
    """Every action an agent may request. Grants are additive and least-privilege."""

    CATALOG_READ = "catalog.read"
    INVENTORY_READ = "inventory.read"
    PRODUCT_READ = "product.read"
    QUOTE_CREATE = "quote.create"
    QUOTE_RESPOND = "quote.respond"
    DEAL_NEGOTIATE = "deal.negotiate"
    CHECKOUT_REQUEST = "checkout.request"
    PAYMENT_REQUEST = "payment.request"
    PAYMENT_MANDATE_CHARGE = "payment.mandate_charge"
    ORDER_READ = "order.read"
    REVIEW_READ = "review.read"
    AUDIT_READ = "audit.read"


class CapabilitySet(BaseModel):
    """The capabilities granted to an agent."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    capabilities: list[Capability] = Field(default_factory=list)

    def has(self, capability: Capability | str) -> bool:
        target = Capability(capability) if isinstance(capability, str) else capability
        return target in self.capabilities
