"""Long-term configuration: loads governance, policies, agent grants, tool registry."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paari.schemas.capability import Capability
from paari.schemas.identity import AgentType
from paari.schemas.policy import PolicyDocument, PolicyLayer


@dataclass(frozen=True)
class AgentGrant:
    agent_id: str
    agent_type: AgentType
    merchant_id: str | None
    capabilities: list[Capability]


@dataclass(frozen=True)
class LongTermConfig:
    """Loaded at startup; read-only at runtime."""

    merchant_id: str
    merchant_name: str
    autonomous_limit_paise: int
    active_hours_utc: list[int]
    average_transaction_paise: int
    policies: dict[PolicyLayer, PolicyDocument] = field(default_factory=dict)
    buyer_grant: AgentGrant | None = None
    merchant_grant: AgentGrant | None = None


_DATA_DIR = Path(__file__).resolve().parents[1] / "governance" / "data"


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((_DATA_DIR / name).read_text(encoding="utf-8"))


def load_long_term_config() -> LongTermConfig:
    """Build the long-term config from the governance data files."""
    from paari.config import settings

    merchant_id = "merchant-demo-001"
    paari_doc = PolicyDocument.model_validate(_load_json("paari_policy.json"))
    merchant_doc = PolicyDocument.model_validate(_load_json("merchant_demo.json"))
    store_doc = PolicyDocument.model_validate(_load_json("store_demo.json"))

    catalog = json.loads(
        (Path(__file__).resolve().parents[1] / "tools" / "fixtures" / "catalog.json").read_text(encoding="utf-8")
    )

    buyer_grant = AgentGrant(
        agent_id="buyer-agent-001",
        agent_type=AgentType.BUYER,
        merchant_id=None,
        capabilities=[
            Capability.CATALOG_READ,
            Capability.INVENTORY_READ,
            Capability.PRODUCT_READ,
            Capability.QUOTE_CREATE,
            Capability.DEAL_NEGOTIATE,
            Capability.PAYMENT_REQUEST,
        ],
    )
    merchant_grant = AgentGrant(
        agent_id="merchant-agent-001",
        agent_type=AgentType.MERCHANT,
        merchant_id=merchant_id,
        capabilities=[Capability.QUOTE_RESPOND, Capability.ORDER_READ, Capability.REVIEW_READ],
    )

    return LongTermConfig(
        merchant_id=merchant_id,
        merchant_name=settings.demo_merchant_name,
        autonomous_limit_paise=settings.demo_merchant_autonomous_limit_paise,
        active_hours_utc=catalog["store"]["active_hours_utc"],
        average_transaction_paise=catalog["average_transaction_paise"],
        policies={
            PolicyLayer.PAARI: paari_doc,
            PolicyLayer.MERCHANT: merchant_doc,
            PolicyLayer.STORE: store_doc,
        },
        buyer_grant=buyer_grant,
        merchant_grant=merchant_grant,
    )
