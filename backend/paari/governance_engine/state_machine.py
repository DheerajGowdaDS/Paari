"""Governance transaction state machine.

15 states with explicit VALID_TRANSITIONS. Any move not in the map raises
IllegalTransitionError. Terminal states reject all transitions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from sqlalchemy import text


class GovernanceTxState(str, Enum):
    """15-state governance transaction machine."""

    CREATED = "CREATED"
    GOVERNANCE_PENDING = "GOVERNANCE_PENDING"
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    RISK_BLOCKED = "RISK_BLOCKED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_VERIFIED = "PAYMENT_VERIFIED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    FULFILLMENT_PENDING = "FULFILLMENT_PENDING"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


_TERMINAL: set[str] = {
    GovernanceTxState.DENIED.value,
    GovernanceTxState.CANCELLED.value,
    GovernanceTxState.EXPIRED.value,
    GovernanceTxState.ARCHIVED.value,
}

VALID_TRANSITIONS: dict[str, list[str]] = {
    GovernanceTxState.CREATED.value: [GovernanceTxState.GOVERNANCE_PENDING.value],
    GovernanceTxState.GOVERNANCE_PENDING.value: [
        GovernanceTxState.AUTHORIZED.value,
        GovernanceTxState.DENIED.value,
        GovernanceTxState.REVIEW_REQUIRED.value,
        GovernanceTxState.RISK_BLOCKED.value,
    ],
    GovernanceTxState.AUTHORIZED.value: [
        GovernanceTxState.PAYMENT_PENDING.value,
        GovernanceTxState.DENIED.value,
        GovernanceTxState.CANCELLED.value,
    ],
    GovernanceTxState.REVIEW_REQUIRED.value: [
        GovernanceTxState.AUTHORIZED.value,
        GovernanceTxState.DENIED.value,
        GovernanceTxState.CANCELLED.value,
    ],
    GovernanceTxState.RISK_BLOCKED.value: [
        GovernanceTxState.REVIEW_REQUIRED.value,
        GovernanceTxState.DENIED.value,
        GovernanceTxState.CANCELLED.value,
    ],
    GovernanceTxState.PAYMENT_PENDING.value: [
        GovernanceTxState.PAYMENT_VERIFIED.value,
        GovernanceTxState.PAYMENT_FAILED.value,
    ],
    GovernanceTxState.PAYMENT_FAILED.value: [
        GovernanceTxState.PAYMENT_PENDING.value,
    ],
    GovernanceTxState.PAYMENT_VERIFIED.value: [
        GovernanceTxState.ORDER_CONFIRMED.value,
        GovernanceTxState.PAYMENT_FAILED.value,
        GovernanceTxState.FULFILLMENT_PENDING.value,
    ],
    # Payment verified but Shopify order creation failed -> retry/reconcile
    GovernanceTxState.FULFILLMENT_PENDING.value: [
        GovernanceTxState.COMPLETED.value,
        GovernanceTxState.PAYMENT_VERIFIED.value,
        GovernanceTxState.CANCELLED.value,
    ],
    GovernanceTxState.ORDER_CONFIRMED.value: [
        GovernanceTxState.COMPLETED.value,
        GovernanceTxState.CANCELLED.value,
    ],
    GovernanceTxState.COMPLETED.value: [
        GovernanceTxState.ARCHIVED.value,
    ],
    GovernanceTxState.DENIED.value: [],
    GovernanceTxState.CANCELLED.value: [],
    GovernanceTxState.EXPIRED.value: [],
    GovernanceTxState.ARCHIVED.value: [],
}

DECISION_TO_STATE: dict[str, str] = {
    "ALLOW": GovernanceTxState.AUTHORIZED.value,
    "DENY": GovernanceTxState.DENIED.value,
    "REVIEW": GovernanceTxState.REVIEW_REQUIRED.value,
}


class IllegalTransitionError(Exception):
    """Raised when a state transition is not in VALID_TRANSITIONS."""

    def __init__(self, tx_id: str, from_state: str, to_state: str) -> None:
        self.tx_id = tx_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"illegal transition for {tx_id}: {from_state} -> {to_state}")


async def walk_to(
    session,
    transaction_id: str,
    target: str | GovernanceTxState,
) -> None:
    """Walk a transaction to ``target`` via legal intermediate states.

    Fresh transactions sit in CREATED, whose only legal move is to
    GOVERNANCE_PENDING — a direct CREATED -> AUTHORIZED/DENIED jump raises
    IllegalTransitionError. This helper inserts the GOVERNANCE_PENDING hop
    when needed so callers don't have to.
    """
    target_str = target.value if isinstance(target, GovernanceTxState) else target
    row = (
        await session.execute(
            text("SELECT id, state FROM transactions WHERE id = :tid"),
            {"tid": transaction_id},
        )
    ).first()
    if row is None:
        raise ValueError(f"transaction not found: {transaction_id}")
    current_state = row.state
    if current_state == target_str:
        return
    if (
        current_state == GovernanceTxState.CREATED.value
        and target_str != GovernanceTxState.GOVERNANCE_PENDING.value
    ):
        await transition(session, transaction_id, GovernanceTxState.GOVERNANCE_PENDING.value)
        current_state = GovernanceTxState.GOVERNANCE_PENDING.value
    if current_state != target_str:
        await transition(session, transaction_id, target_str)


async def transition(
    session,
    transaction_id: str,
    new_state: str | GovernanceTxState,
) -> None:
    """Validate and apply a state transition.

    Args:
        session:       Async SQLAlchemy session (already in a transaction).
        transaction_id: UUID primary key of the transaction.
        new_state:     Target state string or GovernanceTxState member.

    Raises:
        IllegalTransitionError: If the move is not permitted.
        ValueError: If the transaction row is not found.
    """
    new_state_str = new_state.value if isinstance(new_state, GovernanceTxState) else new_state

    row = (
        await session.execute(
            text("SELECT id, state FROM transactions WHERE id = :tid"),
            {"tid": transaction_id},
        )
    ).first()
    if row is None:
        raise ValueError(f"transaction not found: {transaction_id}")

    current_state = row.state

    if current_state in _TERMINAL:
        raise IllegalTransitionError(transaction_id, current_state, new_state_str)

    allowed = VALID_TRANSITIONS.get(current_state, [])
    if new_state_str not in allowed:
        raise IllegalTransitionError(transaction_id, current_state, new_state_str)

    now = datetime.now(UTC).isoformat()
    await session.execute(
        text("UPDATE transactions SET state = :s, updated_at = :ts WHERE id = :tid"),
        {"s": new_state_str, "ts": now, "tid": transaction_id},
    )
