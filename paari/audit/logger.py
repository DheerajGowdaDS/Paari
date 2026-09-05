"""Audit logger: synchronous, append-only event recording.

Every enforcement decision writes an audit_events row BEFORE the HTTP response
returns. If the audit write fails, the request fails (fail-closed). This is
the structural guarantee that "an audit gap means the transaction did not
happen."
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from paari.audit.query import query_audit_events
from paari.schemas.audit import AuditDecision, AuditEvent

_log = logging.getLogger("paari.audit")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AuditLogger:
    """Writes AuditEvent rows to the audit_events table."""

    def __init__(self, session_maker=None) -> None:
        self._session_maker = session_maker

    def _ensure_maker(self):
        if self._session_maker is None:
            from paari.db.engine import get_session_maker

            self._session_maker = get_session_maker()
        return self._session_maker

    async def log(
        self,
        *,
        request_id: str,
        action: str,
        decision: AuditDecision | str,
        agent_id: str | None = None,
        merchant_id: str | None = None,
        policy_version: str | None = None,
        risk_score: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Write one audit event. Returns the event id. Fail-closed on error."""
        maker = self._ensure_maker()
        event_id = str(uuid.uuid4())
        async with maker() as session:
            try:
                await session.execute(
                    text(
                        "INSERT INTO audit_events "
                        "(id, request_id, merchant_id, agent_id, action, decision, policy_version, risk_score, payload_json, created_at) "
                        "VALUES (:id, :request_id, :merchant_id, :agent_id, :action, :decision, :policy_version, :risk_score, :payload_json, :created_at)"
                    ),
                    {
                        "id": event_id,
                        "request_id": request_id,
                        "merchant_id": merchant_id,
                        "agent_id": agent_id,
                        "action": action,
                        "decision": decision.value if isinstance(decision, AuditDecision) else decision,
                        "policy_version": policy_version,
                        "risk_score": risk_score,
                        "payload_json": __import__("json").dumps(payload or {}, default=str),
                        "created_at": _now_iso(),
                    },
                )
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - audit failure is a gateway failure
                _log.error("audit write failed: %s", exc)
                raise
        return event_id

    async def log_event(self, event: AuditEvent) -> str:
        """Log from an AuditEvent schema object."""
        return await self.log(
            request_id=event.request_id,
            action=event.action,
            decision=event.decision,
            agent_id=event.agent_id,
            merchant_id=event.merchant_id,
            policy_version=event.policy_version,
            risk_score=event.risk_score,
            payload=event.payload,
        )

    async def recent(self, merchant_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent audit events (used by the dashboard)."""
        maker = self._ensure_maker()
        async with maker() as session:
            rows = await query_audit_events(session, merchant_id=merchant_id, limit=limit)
            return [dict(r) for r in rows]


# Module-level singleton.
AUDIT = AuditLogger()


def get_audit() -> AuditLogger:
    return AUDIT
