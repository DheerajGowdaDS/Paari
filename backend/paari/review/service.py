"""Review service: create, list, and decide on REVIEW escalations.

When the gateway returns REVIEW_REQUIRED, the runtime loop pauses and creates
a review row holding the pending tool call + gateway context. On APPROVE, the
saved step is re-executed through the gateway (resume from saved plan step).
On DENY (or SLA timeout), the transaction is blocked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from paari.memory.runtime_state import new_id, utcnow

_log = logging.getLogger("paari.review")


def _sla_deadline(hours: int = 4) -> datetime:
    return utcnow() + timedelta(hours=hours)


def _to_sql_ts(dt: datetime) -> str:
    """Render a datetime in SQLite's CURRENT_TIMESTAMP format (UTC, no offset).

    SQLite stores CURRENT_TIMESTAMP as 'YYYY-MM-DD HH:MM:SS' (UTC). ISO-8601
    strings with 'T' and '+00:00' do not string-compare correctly against it,
    so we normalize before storing/comparing.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ReviewRecord:
    id: str
    merchant_id: str
    transaction_id: str
    triggered_by: str  # POLICY | RISK
    reason: str
    sla_expires_at: datetime
    decision: str | None  # null until decided
    decided_by: str | None
    note: str | None
    decided_at: datetime | None
    created_at: datetime
    pending_step: dict[str, Any] | None = None  # saved PlanStep + gateway context
    gateway_context: dict[str, Any] | None = None


def _row_to_record(row: Any) -> ReviewRecord:
    import json as _json

    return ReviewRecord(
        id=row.id,
        merchant_id=row.merchant_id,
        transaction_id=row.transaction_id,
        triggered_by=row.triggered_by,
        reason=row.reason,
        sla_expires_at=row.sla_expires_at,
        decision=row.decision,
        decided_by=row.decided_by,
        note=row.note,
        decided_at=row.decided_at,
        created_at=row.created_at,
        pending_step=_json.loads(row.pending_step_json) if row.pending_step_json else None,
        gateway_context=_json.loads(row.gateway_context_json) if row.gateway_context_json else None,
    )


class ReviewService:
    """Manages the REVIEW queue."""

    def __init__(self, session_maker=None, sla_hours: int = 4) -> None:
        self._session_maker = session_maker
        self._sla_hours = sla_hours

    def _ensure_maker(self):
        if self._session_maker is None:
            from paari.db.engine import get_session_maker

            self._session_maker = get_session_maker()
        return self._session_maker

    async def _ensure_reviews_table(self, session) -> None:
        """Idempotently ensure the reviews table exists (for fresh test DBs)."""
        await session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS reviews ("
                "id CHAR(36) NOT NULL, merchant_id CHAR(36) NOT NULL, transaction_id CHAR(36) NOT NULL, "
                "triggered_by VARCHAR(16) NOT NULL, reason TEXT NOT NULL, sla_expires_at TIMESTAMP NOT NULL, "
                "decision VARCHAR(16), decided_by VARCHAR(64), note TEXT, decided_at TIMESTAMP, "
                "pending_step_json TEXT, gateway_context_json TEXT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "PRIMARY KEY (id))"
            )
        )

    async def create(
        self,
        *,
        merchant_id: str,
        transaction_id: str,
        triggered_by: str,
        reason: str,
        pending_step: dict[str, Any] | None = None,
        gateway_context: dict[str, Any] | None = None,
        sla_hours: int | None = None,
    ) -> ReviewRecord:
        """Create a pending REVIEW row and return it."""
        import json as _json

        maker = self._ensure_maker()
        review_id = new_id()
        sla = _sla_deadline(sla_hours if sla_hours is not None else self._sla_hours)
        async with maker() as session:
            # Ensure the reviews table exists (idempotent; safe for fresh DBs).
            await self._ensure_reviews_table(session)
            await session.execute(
                text(
                    "INSERT INTO reviews (id, merchant_id, transaction_id, triggered_by, reason, sla_expires_at, pending_step_json, gateway_context_json) "
                    "VALUES (:id, :merchant_id, :transaction_id, :triggered_by, :reason, :sla, :pending_step, :gateway_context)"
                ),
                {
                    "id": review_id,
                    "merchant_id": merchant_id,
                    "transaction_id": transaction_id,
                    "triggered_by": triggered_by,
                    "reason": reason,
                    "sla": _to_sql_ts(sla),
                    "pending_step": _json.dumps(pending_step or {}, default=str),
                    "gateway_context": _json.dumps(gateway_context or {}, default=str),
                },
            )
            await session.commit()
        return ReviewRecord(
            id=review_id,
            merchant_id=merchant_id,
            transaction_id=transaction_id,
            triggered_by=triggered_by,
            reason=reason,
            sla_expires_at=sla,
            decision=None,
            decided_by=None,
            note=None,
            decided_at=None,
            created_at=utcnow(),
            pending_step=pending_step,
            gateway_context=gateway_context,
        )

    async def list_pending(self, merchant_id: str | None = None, limit: int = 100) -> list[ReviewRecord]:
        """List pending reviews, oldest first (SLA urgency)."""
        maker = self._ensure_maker()
        async with maker() as session:
            await self._ensure_reviews_table(session)
            where = "WHERE decision IS NULL"
            params: dict[str, Any] = {"limit": limit}
            if merchant_id is not None:
                where += " AND merchant_id = :merchant_id"
                params["merchant_id"] = merchant_id
            rows = (
                await session.execute(
                    text(
                        f"SELECT id, merchant_id, transaction_id, triggered_by, reason, sla_expires_at, decision, decided_by, note, decided_at, created_at, pending_step_json, gateway_context_json "
                        f"FROM reviews {where} ORDER BY sla_expires_at ASC LIMIT :limit"
                    ),
                    params,
                )
            ).fetchall()
            return [_row_to_record(r) for r in rows]

    async def get(self, review_id: str) -> ReviewRecord | None:
        maker = self._ensure_maker()
        async with maker() as session:
            await self._ensure_reviews_table(session)
            row = (
                await session.execute(
                    text(
                        "SELECT id, merchant_id, transaction_id, triggered_by, reason, sla_expires_at, decision, decided_by, note, decided_at, created_at, pending_step_json, gateway_context_json "
                        "FROM reviews WHERE id = :id"
                    ),
                    {"id": review_id},
                )
            ).first()
            return _row_to_record(row) if row else None

    async def decide(self, review_id: str, decision: str, decided_by: str, note: str | None = None) -> ReviewRecord | None:
        """Approve or deny a review. On APPROVE, re-execute the pending step
        through the gateway (full re-checks — policy is re-evaluated, not skipped).
        Returns the updated record, or None if not found."""
        import json as _json

        maker = self._ensure_maker()
        async with maker() as session:
            await self._ensure_reviews_table(session)
            row = (
                await session.execute(
                    text(
                        "SELECT id, merchant_id, transaction_id, triggered_by, reason, sla_expires_at, decision, decided_by, note, decided_at, created_at, pending_step_json, gateway_context_json "
                        "FROM reviews WHERE id = :id"
                    ),
                    {"id": review_id},
                )
            ).first()
            if row is None:
                return None
            if row.decision is not None:
                return _row_to_record(row)  # already decided

            # Update the review row with the decision.
            await session.execute(
                text(
                    "UPDATE reviews SET decision = :decision, decided_by = :decided_by, note = :note, decided_at = CURRENT_TIMESTAMP "
                    "WHERE id = :id"
                ),
                {"id": review_id, "decision": decision, "decided_by": decided_by, "note": note},
            )
            await session.commit()

            # On APPROVE, re-execute the pending step through the gateway.
            if decision == "APPROVE" and row.pending_step_json:
                await self._resume_execution(
                    review_id=review_id,
                    transaction_id=row.transaction_id,
                    pending_step_json=row.pending_step_json,
                    gateway_context_json=row.gateway_context_json,
                )

            updated = (
                await session.execute(
                    text(
                        "SELECT id, merchant_id, transaction_id, triggered_by, reason, sla_expires_at, decision, decided_by, note, decided_at, created_at, pending_step_json, gateway_context_json "
                        "FROM reviews WHERE id = :id"
                    ),
                    {"id": review_id},
                )
            ).first()
            return _row_to_record(updated) if updated else None

    async def _resume_execution(
        self,
        review_id: str,
        transaction_id: str,
        pending_step_json: str,
        gateway_context_json: str | None,
    ) -> None:
        """Re-execute the saved step through the gateway after APPROVE."""
        import json as _json

        from paari.memory.runtime_state import new_id

        pending_step = _json.loads(pending_step_json)
        gw_ctx_data = _json.loads(gateway_context_json) if gateway_context_json else {}

        tool_name = pending_step.get("tool_name", "")
        arguments = pending_step.get("arguments", {})

        # Reconstruct a GatewayContext from the saved data.
        from paari.authn.jwt_verifier import Identity
        from paari.schemas.identity import AgentType
        from paari.tools.gateway import GatewayContext

        identity_data = gw_ctx_data.get("identity", {})
        identity = Identity(
            agent_id=identity_data.get("agent_id", "unknown"),
            agent_type=AgentType(identity_data.get("agent_type", "BUYER")),
            merchant_scope=None,
            capabilities=identity_data.get("capabilities", []),
            policy_version=identity_data.get("policy_version", "v1"),
            jti="review-resume",
        )
        ctx = GatewayContext(
            identity=identity,
            merchant_id=gw_ctx_data.get("merchant_id", "unknown"),
            request_id=new_id(),
            transaction_id=transaction_id,
            tx_context=gw_ctx_data.get("tx_context", {}),
            merchant_context=gw_ctx_data.get("merchant_context", {}),
        )

        # Execute through the full gateway (re-checks policy, risk, authz).
        from paari.tools.gateway import GATEWAY

        result = await GATEWAY.execute(ctx, tool_name, arguments)

        # Update transaction state based on the result.
        from sqlalchemy import text

        new_state = "COMPLETED" if result.status.value == "OK" else "DENIED"
        maker = self._ensure_maker()
        async with maker() as session:
            try:
                await session.execute(
                    text("UPDATE transactions SET state = :state, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                    {"id": transaction_id, "state": new_state},
                )
                await session.commit()
            except Exception as e:
                _log.warning("Failed to update transaction %s: %s", transaction_id, e)

        _log.info(
            "Review %s APPROVED: resumed %s -> %s (transaction=%s)",
            review_id, tool_name, new_state, transaction_id,
        )

    async def auto_deny_expired(self) -> int:
        """Auto-deny any review past its SLA. Returns the count denied."""
        maker = self._ensure_maker()
        async with maker() as session:
            await self._ensure_reviews_table(session)
            result = await session.execute(
                text(
                    "UPDATE reviews SET decision = 'DENY', decided_by = 'system', note = 'sla_timeout', decided_at = CURRENT_TIMESTAMP "
                    "WHERE decision IS NULL AND sla_expires_at < CURRENT_TIMESTAMP"
                )
            )
            await session.commit()
            return result.rowcount or 0


# Module-level singleton.
REVIEW = ReviewService()


def get_review() -> ReviewService:
    return REVIEW
