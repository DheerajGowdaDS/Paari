"""Governance context — frozen record dataclasses + GovernanceContext.

Context composes all data needed by the 10 rule checks and adapters for
the existing PolicyEngine and RiskEngine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ── frozen record dataclasses ───────────────────────────────────────


@dataclass(frozen=True)
class AgentRecord:
    id: str
    display_id: str
    merchant_id: str | None
    agent_type: str
    capabilities: list[str]
    owner_id: str | None
    status: str = "ACTIVE"
    created_at: str = ""


@dataclass(frozen=True)
class MerchantRecord:
    id: str
    display_id: str
    name: str
    status: str
    agent_transactions_enabled: int
    avg_transaction_paise: int
    autonomous_limit_paise: int
    active_hours_utc: list[int]
    created_at: str = ""


@dataclass(frozen=True)
class QuoteRecord:
    id: str
    transaction_id: str
    merchant_id: str
    amount_paise: int
    state: str
    expires_at: str
    created_at: str = ""


@dataclass(frozen=True)
class TransactionRecord:
    id: str
    display_id: str
    merchant_id: str
    buyer_agent_id: str
    merchant_agent_id: str | None
    quote_id: str | None
    amount_paise: int
    currency: str
    state: str
    policy_version: str
    buyer_credential_json: str | None = None
    mandate_id: str | None = None
    created_at: str = ""


@dataclass(frozen=True)
class MandateRecord:
    id: str
    display_id: str
    user_id: str
    provider: str
    instrument_reference: str
    status: str
    max_per_transaction: int
    daily_limit: int
    allowed_merchants_json: str
    allowed_categories_json: str
    autonomous_enabled: int
    requires_review_above: int
    expires_at: str | None = None
    daily_used_paise: int = 0
    created_at: str = ""


@dataclass(frozen=True)
class UserPolicyRecord:
    id: str
    user_id: str
    max_transaction_amount: int
    daily_spending_limit: int
    autonomous_payment: int
    confirmation_threshold: int
    created_at: str = ""


@dataclass(frozen=True)
class MerchantPolicyRecord:
    id: str
    merchant_id: str
    layer: str
    version: str
    document_json: str = ""


@dataclass(frozen=True)
class PaariPolicyRecord:
    policy_id: str
    version: str
    document_json: str = ""


@dataclass(frozen=True)
class PaymentSessionRecord:
    id: str
    display_id: str
    transaction_id: str
    authorized_amount: int
    currency: str
    status: str
    expires_at: str
    created_at: str = ""


@dataclass(frozen=True)
class PaymentCapabilityRecord:
    id: str
    display_id: str
    transaction_id: str
    action: str
    max_amount: int
    usage: str
    used: int
    created_at: str = ""


class GovernanceLoadError(Exception):
    """Raised when a required row is missing during context load."""


# ── main context ────────────────────────────────────────────────────


@dataclass
class GovernanceContext:
    agent: AgentRecord | None = None
    merchant: MerchantRecord | None = None
    quote: QuoteRecord | None = None
    transaction: TransactionRecord | None = None
    mandate: MandateRecord | None = None
    user_policy: UserPolicyRecord | None = None
    merchant_policy: MerchantPolicyRecord | None = None
    paari_policy: PaariPolicyRecord | None = None
    session: PaymentSessionRecord | None = None
    capability: PaymentCapabilityRecord | None = None
    request_id: str = ""
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    async def load(
        cls,
        session: AsyncSession,
        transaction_id: str,
        request_id: str = "",
    ) -> GovernanceContext:
        """Load all governance records for a transaction by UUID or display_id.

        Raises GovernanceLoadError if the transaction row is missing.
        """
        ctx = cls(request_id=request_id)

        # Resolve transaction — accept UUID or display_id
        try:
            tx_row = (
                await session.execute(
                    text(
                        "SELECT id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, "
                        " quote_id, amount_paise, currency, state, policy_version, buyer_credential_json, mandate_id, created_at "
                        "FROM transactions WHERE id = :x OR display_id = :x"
                    ),
                    {"x": transaction_id},
                )
            ).first()
        except Exception:
            tx_row = (
                await session.execute(
                    text(
                        "SELECT id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, "
                        " quote_id, amount_paise, currency, state, policy_version, buyer_credential_json, created_at "
                        "FROM transactions WHERE id = :x OR display_id = :x"
                    ),
                    {"x": transaction_id},
                )
            ).first()
        if tx_row is None:
            raise GovernanceLoadError(f"transaction not found: {transaction_id}")
        tx_map = tx_row._mapping
        ctx.transaction = TransactionRecord(
            id=tx_map["id"],
            display_id=tx_map["display_id"] or tx_map["id"],
            merchant_id=tx_map["merchant_id"],
            buyer_agent_id=tx_map["buyer_agent_id"],
            merchant_agent_id=tx_map["merchant_agent_id"],
            quote_id=tx_map["quote_id"],
            amount_paise=int(tx_map["amount_paise"]),
            currency=tx_map["currency"] or "INR",
            state=tx_map["state"],
            policy_version=tx_map["policy_version"],
            buyer_credential_json=tx_map["buyer_credential_json"],
            mandate_id=tx_map["mandate_id"] if "mandate_id" in tx_map else None,
            created_at=tx_map["created_at"] or "",
        )

        if ctx.transaction and ctx.transaction.mandate_id:
            try:
                mandate_row = (
                    await session.execute(
                        text(
                            "SELECT id, display_id, user_id, provider, instrument_reference, status, "
                            " max_per_transaction, daily_limit, allowed_merchants_json, allowed_categories_json, "
                            " autonomous_enabled, requires_review_above, expires_at, created_at "
                            "FROM mandates WHERE id = :mid OR display_id = :mid"
                        ),
                        {"mid": ctx.transaction.mandate_id},
                    )
                ).first()
            except Exception:
                mandate_row = None
            if mandate_row:
                m = mandate_row._mapping
                try:
                    usage_row = (
                        await session.execute(
                            text(
                                "SELECT used_paise FROM mandate_daily_usage WHERE mandate_id = :m AND day = :d"
                            ),
                            {
                                "m": m["id"],
                                "d": datetime.now(UTC).strftime("%Y-%m-%d"),
                            },
                        )
                    ).first()
                    daily_used = int(usage_row._mapping["used_paise"] or 0) if usage_row else 0
                except Exception:
                    daily_used = 0
                ctx.mandate = MandateRecord(
                    id=m["id"],
                    display_id=m["display_id"] or m["id"],
                    user_id=m["user_id"],
                    provider=m["provider"] or "RAZORPAY",
                    instrument_reference=m["instrument_reference"],
                    status=m["status"] or "ACTIVE",
                    max_per_transaction=int(m["max_per_transaction"]),
                    daily_limit=int(m["daily_limit"]),
                    allowed_merchants_json=m["allowed_merchants_json"] or "[]",
                    allowed_categories_json=m["allowed_categories_json"] or "[]",
                    autonomous_enabled=int(
                        m["autonomous_enabled"] if m["autonomous_enabled"] is not None else 1
                    ),
                    requires_review_above=int(m["requires_review_above"] or 0),
                    expires_at=m["expires_at"],
                    daily_used_paise=daily_used,
                    created_at=m["created_at"] or "",
                )

        # Agent (buyer)
        if ctx.transaction:
            agent_row = (
                await session.execute(
                    text(
                        "SELECT id, display_id, merchant_id, agent_type, capabilities_json, "
                        " owner_id, status, created_at FROM agents WHERE id = :aid"
                    ),
                    {"aid": ctx.transaction.buyer_agent_id},
                )
            ).first()
            if agent_row:
                m = agent_row._mapping
                caps_raw = m["capabilities_json"] or "[]"
                try:
                    caps = __import__("json").loads(caps_raw)
                except Exception:
                    caps = []
                ctx.agent = AgentRecord(
                    id=m["id"],
                    display_id=m["display_id"] or m["id"],
                    merchant_id=m["merchant_id"],
                    agent_type=m["agent_type"],
                    capabilities=caps,
                    owner_id=m["owner_id"],
                    status=m["status"] or "ACTIVE",
                    created_at=m["created_at"] or "",
                )

        # Merchant
        if ctx.transaction:
            merch_row = (
                await session.execute(
                    text(
                        "SELECT id, display_id, name, status, agent_transactions_enabled, "
                        " avg_transaction_paise, autonomous_limit_paise, active_hours_utc, created_at "
                        "FROM merchants WHERE id = :mid"
                    ),
                    {"mid": ctx.transaction.merchant_id},
                )
            ).first()
            if merch_row:
                m = merch_row._mapping
                try:
                    active = __import__("json").loads(m["active_hours_utc"] or "[]")
                except Exception:
                    active = []
                ctx.merchant = MerchantRecord(
                    id=m["id"],
                    display_id=m["display_id"] or m["id"],
                    name=m["name"],
                    status=m["status"],
                    agent_transactions_enabled=int(m["agent_transactions_enabled"] or 1),
                    avg_transaction_paise=int(m["avg_transaction_paise"] or 0),
                    autonomous_limit_paise=int(
                        m.get("autonomous_limit_paise") or m.get("avg_transaction_paise", 0)
                    ),
                    active_hours_utc=active,
                    created_at=m["created_at"] or "",
                )

        # Quote
        if ctx.transaction and ctx.transaction.quote_id:
            quote_row = (
                await session.execute(
                    text(
                        "SELECT id, transaction_id, merchant_id, amount_paise, state, expires_at, created_at "
                        "FROM quotes WHERE id = :qid"
                    ),
                    {"qid": ctx.transaction.quote_id},
                )
            ).first()
            if quote_row:
                m = quote_row._mapping
                ctx.quote = QuoteRecord(
                    id=m["id"],
                    transaction_id=m["transaction_id"],
                    merchant_id=m["merchant_id"],
                    amount_paise=int(m["amount_paise"]),
                    state=m["state"],
                    expires_at=m["expires_at"] or "",
                    created_at=m["created_at"] or "",
                )

        # User policy (via agent owner_id -> user)
        if ctx.agent and ctx.agent.owner_id:
            up_row = (
                await session.execute(
                    text(
                        "SELECT id, user_id, max_transaction_amount, daily_spending_limit, "
                        " autonomous_payment, confirmation_threshold, created_at "
                        "FROM user_policies WHERE user_id = :uid"
                    ),
                    {"uid": ctx.agent.owner_id},
                )
            ).first()
            if up_row:
                m = up_row._mapping
                ctx.user_policy = UserPolicyRecord(
                    id=m["id"],
                    user_id=m["user_id"],
                    max_transaction_amount=int(m["max_transaction_amount"]),
                    daily_spending_limit=int(m["daily_spending_limit"]),
                    autonomous_payment=int(m["autonomous_payment"]),
                    confirmation_threshold=int(m["confirmation_threshold"]),
                    created_at=m["created_at"] or "",
                )

        # Merchant policy (PAARI layer for this merchant)
        if ctx.transaction:
            mp_row = (
                await session.execute(
                    text(
                        "SELECT id, merchant_id, layer, version, document_json "
                        "FROM policies WHERE merchant_id = :mid AND layer = 'PAARI' AND is_active = 1 "
                        "LIMIT 1"
                    ),
                    {"mid": ctx.transaction.merchant_id},
                )
            ).first()
            if mp_row:
                m = mp_row._mapping
                ctx.merchant_policy = MerchantPolicyRecord(
                    id=m["id"],
                    merchant_id=m["merchant_id"],
                    layer=m["layer"],
                    version=m["version"],
                    document_json=m["document_json"] or "",
                )

        # Paari policy (global — first PAARI policy row)
        pp_row = (
            await session.execute(
                text(
                    "SELECT id AS policy_id, version, document_json FROM policies WHERE layer = 'PAARI' LIMIT 1"
                )
            )
        ).first()
        if pp_row:
            m = pp_row._mapping
            ctx.paari_policy = PaariPolicyRecord(
                policy_id=m["policy_id"],
                version=m["version"],
                document_json=m["document_json"] or "",
            )

        # Payment session (active, linked to this transaction)
        if ctx.transaction:
            ps_row = (
                await session.execute(
                    text(
                        "SELECT id, display_id, transaction_id, authorized_amount, currency, "
                        " status, expires_at, created_at "
                        "FROM payment_sessions WHERE transaction_id = :tid AND status = 'ACTIVE' LIMIT 1"
                    ),
                    {"tid": ctx.transaction.id},
                )
            ).first()
            if ps_row:
                m = ps_row._mapping
                ctx.session = PaymentSessionRecord(
                    id=m["id"],
                    display_id=m["display_id"] or m["id"],
                    transaction_id=m["transaction_id"],
                    authorized_amount=int(m["authorized_amount"]),
                    currency=m["currency"] or "INR",
                    status=m["status"],
                    expires_at=m["expires_at"] or "",
                    created_at=m["created_at"] or "",
                )

        # Payment capability (unused, ONE_TIME, linked to this transaction)
        if ctx.transaction:
            cap_row = (
                await session.execute(
                    text(
                        "SELECT id, display_id, transaction_id, action, max_amount, usage, used, created_at "
                        "FROM payment_capabilities WHERE transaction_id = :tid AND used = 0 LIMIT 1"
                    ),
                    {"tid": ctx.transaction.id},
                )
            ).first()
            if cap_row:
                m = cap_row._mapping
                ctx.capability = PaymentCapabilityRecord(
                    id=m["id"],
                    display_id=m["display_id"] or m["id"],
                    transaction_id=m["transaction_id"],
                    action=m["action"],
                    max_amount=int(m["max_amount"]),
                    usage=m["usage"],
                    used=int(m["used"]),
                    created_at=m["created_at"] or "",
                )

        return ctx

    # ── adapters ─────────────────────────────────────────────────────

    def to_policy_context(self) -> dict[str, Any]:
        """Adapt to paari.policy_engine.PolicyContext fields."""
        tx: dict[str, Any] = {}
        if self.transaction:
            tx = {
                "amount_paise": self.transaction.amount_paise,
                "quantity": 1,
                "discount_pct": 0,
                "international": False,
                "currency": self.transaction.currency,
                "state": self.transaction.state,
            }
        agent: dict[str, Any] = {}
        if self.agent:
            agent = {
                "id": self.agent.id,
                "display_id": self.agent.display_id,
                "type": self.agent.agent_type,
                "capabilities": self.agent.capabilities,
                "owner_id": self.agent.owner_id,
                "status": self.agent.status,
            }
        merchant: dict[str, Any] = {}
        if self.merchant:
            merchant = {
                "id": self.merchant.id,
                "display_id": self.merchant.display_id,
                "status": self.merchant.status,
                "agent_transactions_enabled": self.merchant.agent_transactions_enabled,
                "autonomous_limit_paise": self.merchant.autonomous_limit_paise,
                "average_transaction_paise": self.merchant.avg_transaction_paise,
                "active_hours_utc": self.merchant.active_hours_utc,
            }
        store: dict[str, Any] = {}
        if self.quote:
            store = {
                "quote_state": self.quote.state,
                "quote_amount_paise": self.quote.amount_paise,
                "quote_expires_at": self.quote.expires_at,
            }
        return {"tx": tx, "agent": agent, "merchant": merchant, "store": store}

    def to_risk_context(self) -> dict[str, Any]:
        """Adapt to paari.risk.engine.RiskEngine.evaluate() context."""
        ctx: dict[str, Any] = {}
        if self.transaction:
            ctx["tx"] = {
                "amount_paise": self.transaction.amount_paise,
                "hour_utc": datetime.now(UTC).hour,
                "seconds_since_last": 9999,
                "count_per_minute": 0,
                "requested_cap_in_history": False,
            }
        if self.merchant:
            ctx["merchant"] = {
                "average_transaction_paise": self.merchant.avg_transaction_paise,
                "autonomous_limit_paise": self.merchant.autonomous_limit_paise,
                "active_hours_utc": self.merchant.active_hours_utc,
            }
        if self.agent:
            ctx["agent"] = {
                "age_hours": 72,
                "requested_cap_in_history": "payment.request" in self.agent.capabilities,
            }
        return ctx
