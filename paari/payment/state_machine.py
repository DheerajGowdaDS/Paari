"""Payment-specific state transitions.

Extends the governance state machine with payment-specific states
and transitions for the PAYMENT_PENDING -> PAYMENT_VERIFIED flow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import text


class PaymentState(str, Enum):
    """Payment states tracked independently from transaction states."""
    SESSION_ACTIVE = "SESSION_ACTIVE"
    ORDER_CREATED = "ORDER_CREATED"
    CHECKOUT_INITIATED = "CHECKOUT_INITIATED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"


PAYMENT_VALID_TRANSITIONS: dict[str, list[str]] = {
    PaymentState.SESSION_ACTIVE.value: [
        PaymentState.ORDER_CREATED.value,
        PaymentState.SESSION_EXPIRED.value,
    ],
    PaymentState.ORDER_CREATED.value: [
        PaymentState.CHECKOUT_INITIATED.value,
        PaymentState.SESSION_EXPIRED.value,
    ],
    PaymentState.CHECKOUT_INITIATED.value: [
        PaymentState.PAYMENT_AUTHORIZED.value,
        PaymentState.PAYMENT_FAILED.value,
        PaymentState.SESSION_EXPIRED.value,
    ],
    PaymentState.PAYMENT_AUTHORIZED.value: [
        PaymentState.PAYMENT_CAPTURED.value,
        PaymentState.PAYMENT_FAILED.value,
    ],
    PaymentState.PAYMENT_FAILED.value: [
        PaymentState.SESSION_EXPIRED.value,
    ],
    PaymentState.PAYMENT_CAPTURED.value: [],
    PaymentState.VERIFICATION_PENDING.value: [
        PaymentState.PAYMENT_CAPTURED.value,
        PaymentState.PAYMENT_FAILED.value,
    ],
    PaymentState.SESSION_EXPIRED.value: [],
}


async def transition_payment(
    session,
    payment_session_id: str,
    new_state: str,
) -> None:
    """Transition a payment session to a new state.

    Args:
        session: Async SQLAlchemy session.
        payment_session_id: UUID of the payment session.
        new_state: Target state string.

    Raises:
        ValueError: If payment session not found.
        IllegalPaymentTransition: If transition is not allowed.
    """
    class IllegalPaymentTransition(Exception):
        """Raised when a payment state transition is not allowed."""
        def __init__(self, session_id: str, from_state: str, to_state: str) -> None:
            self.session_id = session_id
            self.from_state = from_state
            self.to_state = to_state
            super().__init__(
                f"illegal payment transition for {session_id}: {from_state} -> {to_state}"
            )

    row = (
        await session.execute(
            text("SELECT id, status FROM payment_sessions WHERE id = :sid"),
            {"sid": payment_session_id},
        )
    ).first()

    if row is None:
        raise ValueError(f"Payment session not found: {payment_session_id}")

    current_state = row.status

    if current_state == PaymentState.SESSION_EXPIRED.value:
        raise IllegalPaymentTransition(payment_session_id, current_state, new_state)

    allowed = PAYMENT_VALID_TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        raise IllegalPaymentTransition(payment_session_id, current_state, new_state)

    await session.execute(
        text("UPDATE payment_sessions SET status = :s WHERE id = :sid"),
        {"s": new_state, "sid": payment_session_id},
    )


def is_session_expired(expires_at: datetime) -> bool:
    """Check if a payment session has expired.

    Args:
        expires_at: Session expiration timestamp.

    Returns:
        True if session is expired.
    """
    return datetime.now(UTC) > expires_at
