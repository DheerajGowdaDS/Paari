"""Read-only audit queries for the dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def query_audit_events(
    session: AsyncSession,
    *,
    merchant_id: str | None = None,
    request_id: str | None = None,
    action: str | None = None,
    decision: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
) -> list[Any]:
    """Query audit events with optional filters, newest first."""
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if merchant_id is not None:
        clauses.append("merchant_id = :merchant_id")
        params["merchant_id"] = merchant_id
    if request_id is not None:
        clauses.append("request_id = :request_id")
        params["request_id"] = request_id
    if action is not None:
        clauses.append("action = :action")
        params["action"] = action
    if decision is not None:
        clauses.append("decision = :decision")
        params["decision"] = decision
    if since is not None:
        clauses.append("created_at >= :since")
        params["since"] = since.isoformat()
    if until is not None:
        clauses.append("created_at <= :until")
        params["until"] = until.isoformat()
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        "SELECT id, request_id, merchant_id, agent_id, action, decision, "
        "policy_version, risk_score, payload_json, created_at "
        f"FROM audit_events{where} ORDER BY created_at DESC LIMIT :limit"
    )
    result = await session.execute(text(sql), params)
    return result.fetchall()
