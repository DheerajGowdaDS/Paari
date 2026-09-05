"""Runtime state: transaction, quote, payment, review state helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from paari.schemas.audit import AuditDecision
from paari.schemas.transaction import PaymentState, QuoteState, TxState


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class RuntimeState:
    """Mutable runtime state for the current request chain."""

    request_id: str = field(default_factory=new_id)
    transaction_id: str | None = None
    quote_id: str | None = None
    payment_id: str | None = None
    review_id: str | None = None
    tx_state: TxState = TxState.REQUESTED
    quote_state: QuoteState = QuoteState.DRAFT
    payment_state: PaymentState = PaymentState.PENDING
    audit_tail: list[tuple[str, AuditDecision]] = field(default_factory=list)


def sla_deadline(hours: int = 4) -> datetime:
    return utcnow() + timedelta(hours=hours)
