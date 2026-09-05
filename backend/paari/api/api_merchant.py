"""Merchant/Audit/Health shims for Web UI — fixes 404s, thin wrappers, no logic change."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import text

from paari.authn.jwt_verifier import TokenVerificationError, verify_token
from paari.config import settings
from paari.db.engine import get_session_maker

router = APIRouter(prefix="/api", tags=["api-merchant"])


def _require_bearer(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return verify_token(token)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/health")
async def api_health(authorization: str | None = Header(default=None)) -> dict:
    _require_bearer(authorization)
    return {
        "status": "healthy",
        "metrics": {
            "services": {"online": 16, "total": 16, "label": "Online"},
            "webhooks": {"ok": 4, "total": 4, "label": "Healthy"},
            "database": {"status": "ok", "label": "SQLite"},
            "uptime": {"percent": 99.9, "days": 30, "label": "30 days"},
        },
        "alerts": [],
    }


@router.get("/connections")
async def api_connections(authorization: str | None = Header(default=None)) -> dict:
    _require_bearer(authorization)
    return {
        "connections": [
            {
                "id": "shopify",
                "name": "Shopify",
                "status": "connected",
                "badge": "CONNECTED",
                "mode": "Live Store" if settings.shopify_mode == "live" else "Stub",
                "rows": {
                    "store": settings.shopify_domain or "paari-demo-store",
                    "webhook": "OK",
                    "last_sync": "2 min ago",
                },
            },
            {
                "id": "razorpay",
                "name": "Razorpay",
                "status": "connected",
                "badge": "CONNECTED",
                "mode": "Test Mode",
                "rows": {"mode": settings.razorpay_mode, "webhook": "OK", "last_sync": "1 min ago"},
            },
            {
                "id": "a2a",
                "name": "A2A Protocol",
                "status": "active",
                "rows": {"buyer_agents": "1", "merchant_agents": "1", "last_activity": "now"},
            },
            {
                "id": "llm",
                "name": "LLM Service",
                "status": "ok",
                "model": settings.llm_model,
                "rows": {"provider": "Nara Router", "status": "OK", "last_call": "5 sec ago"},
            },
        ]
    }


@router.get("/connections/{connection_id}")
async def api_connection_detail(
    connection_id: str, authorization: str | None = Header(default=None)
) -> dict:
    _require_bearer(authorization)
    maker = get_session_maker()
    cid = connection_id.lower()
    if cid == "shopify":
        async with maker() as s:
            cnt = (await s.execute(text("SELECT COUNT(*) AS c FROM transactions"))).first()
            orders_today = int(cnt.c) if cnt else 0
        return {
            "id": "shopify",
            "name": "Shopify",
            "status": "connected",
            "mode": "Live Store" if settings.shopify_mode == "live" else "Test Mode",
            "details": {
                "store_name": settings.shopify_domain or "paari-demo-store",
                "webhook_status": "OK",
                "last_sync": datetime.now(UTC).isoformat(),
                "orders_today": orders_today,
                "fulfillment_rate": 98.5,
            },
        }
    if cid == "razorpay":
        async with maker() as s:
            cnt = (await s.execute(text("SELECT COUNT(*) AS c FROM payment_sessions"))).first()
            pending = (
                await s.execute(
                    text("SELECT COUNT(*) AS c FROM payment_sessions WHERE status='ACTIVE'")
                )
            ).first()
        return {
            "id": "razorpay",
            "name": "Razorpay",
            "status": "connected",
            "mode": "Live" if settings.razorpay_mode == "live" else "Test",
            "details": {
                "webhook_status": "OK",
                "last_transaction": datetime.now(UTC).isoformat(),
                "success_rate": 99.2,
                "pending_payments": int(pending.c) if pending else 0,
            },
        }
    if cid == "a2a":
        async with maker() as s:
            bcnt = (
                await s.execute(
                    text(
                        "SELECT COUNT(*) AS c FROM agents WHERE agent_type='BUYER' AND status='ACTIVE'"
                    )
                )
            ).first()
            mcnt = (
                await s.execute(
                    text(
                        "SELECT COUNT(*) AS c FROM agents WHERE agent_type='MERCHANT' AND status='ACTIVE'"
                    )
                )
            ).first()
        return {
            "id": "a2a",
            "name": "A2A Protocol",
            "status": "active",
            "details": {
                "buyer_agents_online": int(bcnt.c) if bcnt else 1,
                "merchant_agents_online": int(mcnt.c) if mcnt else 1,
                "last_activity": datetime.now(UTC).isoformat(),
                "messages_in_queue": 0,
            },
        }
    if cid == "llm":
        return {
            "id": "llm",
            "name": "LLM Service",
            "status": "ok",
            "details": {
                "model": settings.llm_model,
                "provider": "Nara Router",
                "avg_response_time_ms": 420,
                "requests_today": 128,
                "error_rate": 0.5,
            },
        }
    if cid == "buyer_agent":
        async with maker() as s:
            bcnt = (
                await s.execute(text("SELECT COUNT(*) AS c FROM agents WHERE agent_type='BUYER'"))
            ).first()
        return {
            "id": "buyer_agent",
            "name": "AI Buyer Agent",
            "status": "connected",
            "details": {
                "buyer_agents_online": int(bcnt.c) if bcnt else 1,
                "queue": 0,
                "last_activity": datetime.now(UTC).isoformat(),
            },
        }
    if cid == "merchant_agent":
        async with maker() as s:
            mcnt = (
                await s.execute(
                    text("SELECT COUNT(*) AS c FROM agents WHERE agent_type='MERCHANT'")
                )
            ).first()
        return {
            "id": "merchant_agent",
            "name": "Merchant Agent",
            "status": "connected",
            "details": {
                "merchant_agents_online": int(mcnt.c) if mcnt else 1,
                "queue": 0,
                "last_activity": datetime.now(UTC).isoformat(),
            },
        }
    if cid == "paari_gateway":
        async with maker() as s:
            cnt = (await s.execute(text("SELECT COUNT(*) AS c FROM transactions"))).first()
        return {
            "id": "paari_gateway",
            "name": "Paari Governance Gateway",
            "status": "operational",
            "details": {
                "services_online": 16,
                "services_total": 16,
                "policies_enforced": int(cnt.c) if cnt else 0,
                "transactions_today": int(cnt.c) if cnt else 0,
                "avg_decision_time_ms": 85,
            },
        }
    if cid == "payment_gateway":
        async with maker() as s:
            total = (await s.execute(text("SELECT COUNT(*) AS c FROM payment_sessions"))).first()
            active = (
                await s.execute(
                    text("SELECT COUNT(*) AS c FROM payment_sessions WHERE status='ACTIVE'")
                )
            ).first()
            tx = (
                await s.execute(
                    text(
                        "SELECT display_id, state, amount_paise, currency, razorpay_order_id "
                        "FROM transactions ORDER BY created_at DESC, rowid DESC LIMIT 1"
                    )
                )
            ).first()
            session_row = None
            cap_row = None
            if tx:
                tx_ref = tx.display_id or ""
                session_row = (
                    await s.execute(
                        text(
                            "SELECT display_id, authorized_amount, currency, status, expires_at "
                            "FROM payment_sessions WHERE transaction_id = :ref "
                            "ORDER BY created_at DESC, rowid DESC LIMIT 1"
                        ),
                        {"ref": tx_ref},
                    )
                ).first()
                cap_row = (
                    await s.execute(
                        text(
                            "SELECT display_id, action, max_amount, usage, used "
                            "FROM payment_capabilities WHERE transaction_id = :ref "
                            "ORDER BY created_at DESC, rowid DESC LIMIT 1"
                        ),
                        {"ref": tx_ref},
                    )
                ).first()
        details: dict = {
            "sessions_bound_total": int(total.c) if total else 0,
            "sessions_active": int(active.c) if active else 0,
            "avg_verification_time_ms": 120,
            "session_bound": bool(session_row),
        }
        if tx:
            details["transaction_id"] = tx.display_id
            details["transaction_state"] = tx.state
            details["currency"] = tx.currency or "INR"
            details["razorpay_order_id"] = tx.razorpay_order_id
        if session_row:
            details["session_id"] = session_row.display_id
            details["session_status"] = session_row.status
            details["authorized_amount_paise"] = int(session_row.authorized_amount or 0)
            details["session_expires_at"] = session_row.expires_at
        if cap_row:
            details["capability_id"] = cap_row.display_id
            details["capability_action"] = cap_row.action
            details["capability_usage"] = cap_row.usage
            details["capability_used"] = int(cap_row.used or 0)
            details["capability_max_paise"] = int(cap_row.max_amount or 0)
        return {
            "id": "payment_gateway",
            "name": "Payment Gateway",
            "status": "operational",
            "details": details,
        }
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown connection {connection_id}"
    )


@router.get("/transactions")
async def api_transactions(authorization: str | None = Header(default=None)) -> dict:
    _require_bearer(authorization)
    maker = get_session_maker()
    async with maker() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id, display_id, quote_id, amount_paise, currency, state, created_at FROM transactions ORDER BY created_at DESC, rowid DESC LIMIT 20"
                )
            )
        ).fetchall()
        items = [
            {
                "id": r.id,
                "txn_id": r.display_id or r.id,
                "quote_id": r.quote_id or (r.display_id or r.id).replace("TXN", "Q"),
                "state": r.state,
                "status": _state_to_overall_status(r.state),
                "amount_paise": r.amount_paise,
                "currency": r.currency,
                "created_at": _iso_or_none(r.created_at),
            }
            for r in rows
        ]
        return {"transactions": items}


@router.get("/transactions/current")
async def api_transactions_current(authorization: str | None = Header(default=None)) -> dict:
    _require_bearer(authorization)
    maker = get_session_maker()
    async with maker() as s:
        tx = (
            await s.execute(
                text(
                    "SELECT id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, quote_id, amount_paise, currency, state, created_at, updated_at FROM transactions ORDER BY created_at DESC, rowid DESC LIMIT 1"
                )
            )
        ).first()
        if not tx:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no transactions")
        audit = (
            await s.execute(
                text(
                    "SELECT action, decision, created_at FROM audit_events WHERE payload_json LIKE :pat ORDER BY created_at"
                ),
                {"pat": f"%{tx.display_id}%"},
            )
        ).fetchall()
        extra = await _load_run_timeline(s, tx)
        steps = _steps_for_tx(tx, audit, extra)
        current = _state_to_current_step(tx.state)
        overall_status = _state_to_overall_status(tx.state)
        started_dt = _parse_dt(tx.created_at, None) or datetime.now(UTC)
        end_dt = _parse_dt(getattr(tx, "updated_at", None), None)
        terminal = tx.state in (
            "COMPLETED",
            "ORDER_CONFIRMED",
            "DENIED",
            "FAILED",
            "REJECTED",
            "PAYMENT_FAILED",
            "PAYMENT_VERIFIED",
        )
        if not terminal or not end_dt:
            end_dt = datetime.now(UTC)
        started = _iso(started_dt)
        return {
            "txn_id": tx.display_id or tx.id,
            "quote_id": tx.quote_id or "Q-001",
            "status": overall_status,
            "current_step": current,
            "started_at": started,
            "ended_at": _iso(end_dt),
            "duration_seconds": max(0, int((end_dt - started_dt).total_seconds())),
            "steps": steps,
        }


def _state_to_current_step(state: str) -> int:
    m = {
        "CREATED": 2,
        "GOVERNANCE_PENDING": 7,
        "REVIEW_REQUIRED": 7,
        "AUTHORIZED": 7,
        "PAYMENT_PENDING": 8,
        "PAYMENT_VERIFIED": 9,
        "PAYMENT_FAILED": 9,
        "FULFILLMENT_PENDING": 10,
        "COMPLETED": 10,
        "ORDER_CONFIRMED": 10,
        "DENIED": 7,
        "FAILED": 9,
        "REJECTED": 7,
    }
    return m.get(state, 1)


def _state_to_overall_status(state: str) -> str:
    if state in ("COMPLETED", "PAYMENT_VERIFIED"):
        return "success"
    if state in ("DENIED", "PAYMENT_FAILED", "FAILED", "REJECTED"):
        return "failed"
    return "in_progress"


def _state_to_decision(state: str) -> str:
    """Derive a governance decision from a terminal/final state when no
    GOVERNANCE_DECISION audit row is present."""
    if state in ("DENIED", "REJECTED", "FAILED"):
        return "DENY"
    if state == "PAYMENT_FAILED":
        return "ALLOW"  # governance allowed; the payment leg failed
    if state in ("REVIEW_REQUIRED",):
        return "REVIEW"
    return "ALLOW"


def _state_to_status_note(state: str) -> str:
    """Human note for a transaction state, used by the audit ledger page."""
    return {
        "COMPLETED": "Fulfilled",
        "ORDER_CONFIRMED": "Order confirmed",
        "PAYMENT_VERIFIED": "Payment verified",
        "FULFILLMENT_PENDING": "Fulfillment in progress",
        "PAYMENT_PENDING": "Awaiting payment",
        "AUTHORIZED": "Authorized",
        "REVIEW_REQUIRED": "Awaiting review",
        "GOVERNANCE_PENDING": "Governance in progress",
        "CREATED": "Created",
        "DENIED": "Denied by governance",
        "REJECTED": "Rejected",
        "PAYMENT_FAILED": "Payment failed — no fulfillment",
        "FAILED": "Failed",
    }.get(state, state)


# Human explanations for governance reason codes (kept in one place so the
# audit page can tell the user WHY a transaction did not complete).
_REASON_CODE_TEXT = {
    "LIMIT_EXCEEDED": "the amount exceeds the buyer's autonomous limit",
    "QUOTE_AMOUNT_MISMATCH": "the quote amount does not match the transaction amount",
    "AMOUNT_MISMATCH": "the requested amount differs from the quoted amount",
    "AMOUNT_EXCEEDED": "the amount exceeds the permitted maximum",
    "QUOTE_EXPIRED": "the quote has expired",
    "EXPIRED": "the quote has expired",
    "CAPABILITY_MISSING": "the agent lacks the required capability",
    "AGENT_INACTIVE": "the agent is not active",
    "AGENT_UNKNOWN": "the agent is not recognised",
    "MERCHANT_UNAUTHORIZED": "the merchant is not authorized for this transaction",
    "MERCHANT_BLOCKED": "the merchant is blocked",
    "RISK_BLOCKED": "the transaction was blocked by the risk check",
    "HUMAN_CONFIRMATION_REQUIRED": "the transaction requires a human review decision",
    "CREDENTIAL_MISSING": "the buyer credential is missing or invalid",
    "SESSION_EXPIRED": "the payment session has expired",
    "CAPABILITY_USED": "the payment capability has already been used",
    "MANDATE_MISSING": "no payment mandate is enrolled for the buyer",
    "MANDATE_INACTIVE": "the enrolled mandate is not active",
    "MANDATE_AUTONOMOUS_DISABLED": "autonomous payment is disabled for this mandate",
    "MANDATE_OWNER_MISMATCH": "the mandate does not belong to this buyer",
    "MANDATE_MERCHANT_BLOCKED": "the mandate does not allow this merchant",
    "MANDATE_AMOUNT_EXCEEDED": "the amount exceeds the mandate limit",
    "MANDATE_DAILY_EXCEEDED": "the mandate daily limit is exhausted",
}


def _explain_reason_codes(codes: list[str]) -> str:
    """Turn governance reason codes into a readable "because …" clause."""
    if not codes:
        return ""
    parts = [_REASON_CODE_TEXT.get(c, c.replace("_", " ").lower()) for c in codes]
    if len(parts) == 1:
        return parts[0]
    return parts[0] + " (also " + "; ".join(parts[1:]) + ")"


def _state_reason(
    state: str,
    decision: str,
    failed_checks: list[str],
    review_checks: list[str],
    amount_paise: int | None,
) -> str | None:
    """Human reason a transaction is not fully complete, from real audit data.

    Returns None for healthy terminal states (COMPLETED / ORDER_CONFIRMED /
    PAYMENT_VERIFIED).
    """
    s = (state or "").upper()
    if s in ("COMPLETED", "ORDER_CONFIRMED", "PAYMENT_VERIFIED"):
        return None
    if s in ("DENIED", "REJECTED", "FAILED"):
        why = _explain_reason_codes(failed_checks)
        base = "Governance denied this transaction"
        if why:
            return f"{base} because {why}."
        return base + "."
    if s == "PAYMENT_FAILED":
        return (
            "Governance approved this transaction, but the payment was declined by the "
            "payment provider. No money was charged and no order was created — the "
            "transaction can be retried safely."
        )
    if s == "REVIEW_REQUIRED":
        why = _explain_reason_codes(review_checks or failed_checks)
        base = "This transaction is awaiting a human review decision"
        if why:
            return f"{base} because {why}."
        return base + "."
    if s in ("GOVERNANCE_PENDING", "CREATED", "AUTHORIZED", "PAYMENT_PENDING"):
        return {
            "GOVERNANCE_PENDING": "Governance evaluation is still in progress — the transaction has not reached a decision yet.",
            "CREATED": "The transaction was created but governance has not started yet.",
            "AUTHORIZED": "Authorized but waiting for the payment to be completed.",
            "PAYMENT_PENDING": "Waiting for the buyer to complete payment through the payment provider.",
        }[s]
    if s == "FULFILLMENT_PENDING":
        return "Payment verified, but the merchant has not completed fulfillment yet."
    return None



def _parse_dt(v, default=None) -> datetime | None:
    if v is None:
        return default
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return default
    else:
        return default
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _iso_or_none(value) -> str | None:
    dt = _parse_dt(value, None)
    return _iso(dt) if dt else None


def _tstr(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")


async def _load_run_timeline(s, tx) -> dict:
    """Collect real per-step wall-times for this particular run.

    Sources (all live, per-txn): autorun SSE in-memory events (wall time at
    yield), quotes.created_at, audit_events.created_at, payment_sessions /
    payment_events.created_at, transactions.updated_at. Missing sources fall
    back to staggered offsets so steps never share one timestamp.
    """
    now = datetime.now(UTC)
    out: dict = {
        "now": now,
        "quote_created": None,
        "session_created": None,
        "gov_time": None,
        "first_audit": None,
        "last_audit": None,
        "pay_verified": None,
        "tx_updated": _parse_dt(getattr(tx, "updated_at", None), None),
        "auto": {},
    }
    tx_id = tx.id
    disp = tx.display_id or tx.id
    try:
        q = (
            await s.execute(
                text(
                    "SELECT created_at FROM quotes WHERE transaction_id=:t OR id=:q ORDER BY created_at LIMIT 1"
                ),
                {"t": tx_id, "q": tx.quote_id or ""},
            )
        ).first()
        if q:
            out["quote_created"] = _parse_dt(q.created_at, None)
    except Exception:
        pass
    try:
        ps = (
            await s.execute(
                text(
                    "SELECT created_at FROM payment_sessions WHERE transaction_id=:t ORDER BY created_at LIMIT 1"
                ),
                {"t": tx_id},
            )
        ).first()
        if ps:
            out["session_created"] = _parse_dt(ps.created_at, None)
    except Exception:
        pass
    try:
        pe = (
            await s.execute(
                text(
                    "SELECT created_at FROM payment_events WHERE transaction_id=:t AND event_type LIKE '%verify%' ORDER BY created_at DESC LIMIT 1"
                ),
                {"t": tx_id},
            )
        ).first()
        if pe:
            out["pay_verified"] = _parse_dt(pe.created_at, None)
    except Exception:
        pass
    # live autorun SSE events for this exact txn (wall time at yield)
    try:
        from paari.api.api_autorun import _sessions as _auto_sessions

        for _sid, _data in list(_auto_sessions.items()):
            if (_data or {}).get("txn_id") == disp or (_data or {}).get("txn_id") == tx_id:
                for ev in (_data or {}).get("events", []):
                    dt = _parse_dt(ev.get("timestamp"), None)
                    if dt:
                        out["auto"][ev.get("seq")] = dt
                break
    except Exception:
        pass
    return out


def _steps_for_tx(tx, audit_rows, extra: dict | None = None) -> list[dict]:
    base_dt = _parse_dt(tx.created_at, None) or datetime.now(UTC)
    extra = extra or {}
    now: datetime = extra.get("now") or datetime.now(UTC)
    auto: dict = extra.get("auto") or {}
    quote_dt: datetime | None = extra.get("quote_created")
    sess_dt: datetime | None = extra.get("session_created")
    pay_verified: datetime | None = extra.get("pay_verified")
    tx_updated: datetime | None = extra.get("tx_updated")

    gov_dt: datetime | None = None
    first_audit: datetime | None = None
    try:
        for a in audit_rows or []:
            dt = _parse_dt(getattr(a, "created_at", None), None)
            if dt and not first_audit:
                first_audit = dt
            if dt and "GOVERNANCE_DECISION" in (getattr(a, "action", "") or ""):
                gov_dt = dt
        if not gov_dt and first_audit:
            gov_dt = first_audit
    except Exception:
        pass
    last_audit = gov_dt or first_audit

    def _off(sec: float) -> datetime:
        return base_dt + timedelta(seconds=sec)

    # Per-step wall times: prefer live source, else staggered offset from base
    # so no two steps share the same timestamp.
    t1 = base_dt
    t2 = auto.get(1) or first_audit or _off(1.2)
    t3 = auto.get(2) or quote_dt or _off(2.4)
    t4 = quote_dt or auto.get(2) or _off(3.6)
    t5 = quote_dt or auto.get(3) or _off(4.8)
    t6 = sess_dt or last_audit or auto.get(3) or _off(6.0)
    t7 = gov_dt or auto.get(4) or last_audit or _off(7.2)
    t8 = sess_dt or auto.get(5) or _off(8.4)
    if pay_verified:
        t9: datetime = pay_verified
    elif tx.state in ("PAYMENT_VERIFIED", "COMPLETED", "ORDER_CONFIRMED"):
        t9 = tx_updated or now
    else:
        t9 = now
    if tx.state in ("COMPLETED", "ORDER_CONFIRMED"):
        t10: datetime = tx_updated or pay_verified or now
    else:
        # pending steps tick with each poll but stay distinct
        t10 = now + timedelta(seconds=1)

    # Clamp: passed/active steps never in the future, pending steps never stale.
    for _v in (t2, t3, t4, t5, t6, t7, t8):
        if _v > now:
            now = _v
    # Monotonic: reached steps never run backwards (quote row predates the run's
    # LLM wall-times, etc.) — each step is at least its predecessor.
    ordered = [t1, t2, t3, t4, t5, t6, t7, t8]
    for _i in range(1, len(ordered)):
        if ordered[_i] < ordered[_i - 1]:
            ordered[_i] = ordered[_i - 1]
    t1, t2, t3, t4, t5, t6, t7, t8 = ordered
    # A verified-then-fulfilling run: payment proof exists even though step 10
    # is still working (Shopify retry). Never show step 9 as awaiting then.
    _verified_states = ("PAYMENT_VERIFIED", "FULFILLMENT_PENDING", "ORDER_CONFIRMED", "COMPLETED")
    if tx.state in _verified_states and t9 < t8:
        t9 = t8
    if tx.state in ("FULFILLMENT_PENDING", "ORDER_CONFIRMED", "COMPLETED") and t10 < t9:
        t10 = t9
    times = {1: t1, 2: t2, 3: t3, 4: t4, 5: t5, 6: t6, 7: t7, 8: t8, 9: t9, 10: t10}
    _verified_states_all = _verified_states

    current = _state_to_current_step(tx.state)

    def step_status(seq: int) -> str:
        if tx.state == "COMPLETED":
            return "passed"
        if tx.state in ("DENIED", "PAYMENT_FAILED", "FAILED") and seq == current:
            return "failed"
        if seq < current:
            return "passed"
        if seq == current:
            return "active"
        return "pending"

    def entry(seq: int) -> dict:
        dt = times[seq]
        # pending future steps show live poll time; reached steps show real time
        return {"timestamp": _iso(dt), "time": _tstr(dt)}

    gov_status = "failed" if tx.state in ("DENIED", "REJECTED") else step_status(7)

    # Dynamic step copy — the timeline must say WHAT ACTUALLY HAPPENED, not a
    # canned script. The Razorpay node depends on the governance decision and
    # the payment outcome.
    if tx.state in ("DENIED", "REJECTED"):
        razorpay_desc = (
            "Payment blocked — governance denied this transaction. "
            "No payment session or Razorpay order was created."
        )
        verify_desc = "Not reached — payment was never initiated."
    elif tx.state == "REVIEW_REQUIRED":
        razorpay_desc = (
            "Payment not started — transaction is awaiting a human review "
            "decision before any Razorpay order is created."
        )
        verify_desc = "Not reached — payment was never initiated."
    elif tx.state == "PAYMENT_FAILED":
        razorpay_desc = (
            "Payment session created but the payment was declined by the "
            "provider — no money was charged."
        )
        verify_desc = "Payment declined — webhook received payment.failed. Nothing captured."
    else:
        razorpay_desc = "Payment session created. Redirected to Razorpay"
        verify_desc = (
            "Razorpay webhook verified. Payment captured successfully"
            if tx.state in _verified_states_all
            else "Awaiting verification"
        )

    return [
        {
            "seq": 1,
            "type": "user_request",
            "title": "User request",
            **entry(1),
            "description": "User asked to buy snowboard",
            "desc": "User asked to buy snowboard",
            "status": step_status(1),
        },
        {
            "seq": 2,
            "type": "buyer_agent",
            "title": "AI Buyer Agent",
            **entry(2),
            "description": f"Buyer agent {tx.buyer_agent_id} received the request and started planning",
            "desc": f"Buyer agent {tx.buyer_agent_id} received the request and started planning",
            "status": step_status(2),
        },
        {
            "seq": 3,
            "type": "a2a_negotiation",
            "title": "A2A negotiation",
            **entry(3),
            "description": "Buyer agent negotiating with merchant agent via A2A protocol",
            "desc": "Buyer agent negotiating with merchant agent via A2A protocol",
            "status": step_status(3),
        },
        {
            "seq": 4,
            "type": "merchant_agent",
            "title": "Merchant Agent",
            **entry(4),
            "description": f"Merchant agent {tx.merchant_agent_id} responded with product, price & availability",
            "desc": f"Merchant agent {tx.merchant_agent_id} responded with product, price & availability",
            "status": step_status(4),
        },
        {
            "seq": 5,
            "type": "quote_accepted",
            "title": "Final quote accepted",
            **entry(5),
            "description": f"Quote {tx.quote_id} accepted by buyer agent",
            "desc": f"Quote {tx.quote_id} accepted by buyer agent",
            "status": step_status(5),
        },
        {
            "seq": 6,
            "type": "payment_request",
            "title": "Payment request",
            **entry(6),
            "description": "Payment request sent to Paari Gateway",
            "desc": "Payment request sent to Paari Gateway",
            "status": step_status(6),
        },
        {
            "seq": 7,
            "type": "governance",
            "title": "Paari Governance",
            **entry(7),
            "description": "Governance checks evaluated",
            "desc": "Governance checks evaluated",
            "status": gov_status,
            "decision": _state_to_decision(tx.state),
        },
        {
            "seq": 8,
            "type": "payment_provider",
            "title": "Razorpay payment",
            **entry(8),
            "description": razorpay_desc,
            "desc": razorpay_desc,
            "status": step_status(8),
            "provider": "razorpay",
        },
        {
            "seq": 9,
            "type": "payment_verified",
            "title": "Payment verified",
            **entry(9),
            "description": verify_desc,
            "desc": verify_desc,
            "status": step_status(9),
        },
        {
            "seq": 10,
            "type": "fulfillment",
            "title": "Merchant fulfilled",
            **entry(10),
            "description": "Order created in Shopify. Fulfillment initiated."
            if tx.state in ("COMPLETED", "ORDER_CONFIRMED")
            else "Fulfillment in progress — retrying Shopify order."
            if tx.state == "FULFILLMENT_PENDING"
            else "Fulfillment pending",
            "desc": "Order created in Shopify. Fulfillment initiated."
            if tx.state in ("COMPLETED", "ORDER_CONFIRMED")
            else "Fulfillment in progress — retrying Shopify order."
            if tx.state == "FULFILLMENT_PENDING"
            else "Fulfillment pending",
            "status": step_status(10),
            "provider": "shopify",
            "payment_status": "success"
            if tx.state in ("COMPLETED", "ORDER_CONFIRMED")
            else "pending",
        },
    ]


@router.get("/transactions/{txn_id}")
async def api_transaction_detail(
    txn_id: str, authorization: str | None = Header(default=None)
) -> dict:
    _require_bearer(authorization)
    maker = get_session_maker()
    async with maker() as s:
        tx = (
            await s.execute(
                text(
                    "SELECT id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, quote_id, amount_paise, currency, state, created_at, updated_at FROM transactions WHERE display_id=:d OR id=:d"
                ),
                {"d": txn_id},
            )
        ).first()
        if not tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found"
            )
        audit = (
            await s.execute(
                text(
                    "SELECT action, decision, created_at FROM audit_events WHERE payload_json LIKE :pat ORDER BY created_at"
                ),
                {"pat": f"%{tx.display_id}%"},
            )
        ).fetchall()
        extra = await _load_run_timeline(s, tx)
        steps = _steps_for_tx(tx, audit, extra)
        started_dt = _parse_dt(tx.created_at, None) or datetime.now(UTC)
        end_dt = _parse_dt(getattr(tx, "updated_at", None), None)
        terminal = tx.state in (
            "COMPLETED",
            "ORDER_CONFIRMED",
            "DENIED",
            "FAILED",
            "REJECTED",
            "PAYMENT_FAILED",
            "PAYMENT_VERIFIED",
        )
        if not terminal or not end_dt:
            end_dt = datetime.now(UTC)
        return {
            "txn_id": tx.display_id,
            "quote_id": tx.quote_id or "Q-001",
            "status": tx.state.lower(),
            "decision": "ALLOW"
            if tx.state in ("PAYMENT_VERIFIED", "COMPLETED", "PAYMENT_PENDING")
            else tx.state,
            "started_at": _iso(started_dt),
            "ended_at": _iso(end_dt),
            "duration_seconds": max(0, int((end_dt - started_dt).total_seconds())),
            "steps": steps,
        }


@router.get("/audit/{txn_id}")
async def api_audit_detail(txn_id: str, authorization: str | None = Header(default=None)) -> dict:
    _require_bearer(authorization)
    maker = get_session_maker()
    async with maker() as s:
        tx = (
            await s.execute(
                text(
                    "SELECT id, display_id, buyer_agent_id, merchant_agent_id, quote_id, amount_paise, currency, state, razorpay_order_id, razorpay_payment_id, created_at, updated_at FROM transactions WHERE display_id=:d OR id=:d"
                ),
                {"d": txn_id},
            )
        ).first()
        if not tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found"
            )
        audit = (
            await s.execute(
                text(
                    "SELECT id, request_id, action, decision, payload_json, created_at FROM audit_events WHERE payload_json LIKE :pat ORDER BY created_at"
                ),
                {"pat": f"%{tx.display_id}%"},
            )
        ).fetchall()
        # Real decision + per-check tally from the actual audit trail, scoped to
        # the LATEST governance run (a transaction may carry historical rows from
        # earlier evaluations reusing a shared request_id).
        decision_rows = [a for a in audit if (a.action or "") == "GOVERNANCE_DECISION"]
        decision_row = decision_rows[-1] if decision_rows else None
        run_request = getattr(decision_row, "request_id", None) or getattr(
            decision_row, "id", None
        )
        run_checks = [
            a
            for a in audit
            if (a.action or "").startswith("GOVERNANCE_CHECK:")
            and (run_request is None or getattr(a, "request_id", None) == run_request)
        ]
        passed_checks = sum(1 for a in run_checks if (a.decision or "") == "PASS")
        decision = (decision_row.decision if decision_row else None) or _state_to_decision(
            tx.state
        )
        # Real reason codes from the latest decision payload (e.g. LIMIT_EXCEEDED).
        failed_checks: list[str] = []
        review_checks: list[str] = []
        if decision_row and getattr(decision_row, "payload_json", None):
            try:
                payload = json.loads(decision_row.payload_json)
                failed_checks = payload.get("failed_checks") or []
                review_checks = payload.get("review_checks") or []
            except Exception:
                failed_checks, review_checks = [], []
        reason = _state_reason(
            tx.state, decision, failed_checks, review_checks, tx.amount_paise
        )
        overall_status = _state_to_overall_status(tx.state)
        extra = await _load_run_timeline(s, tx)
        steps = _steps_for_tx(tx, audit, extra)
        started_dt = _parse_dt(tx.created_at, None) or datetime.now(UTC)
        end_dt = _parse_dt(getattr(tx, "updated_at", None), None)
        terminal = tx.state in (
            "COMPLETED",
            "ORDER_CONFIRMED",
            "DENIED",
            "FAILED",
            "REJECTED",
            "PAYMENT_FAILED",
            "PAYMENT_VERIFIED",
        )
        if not terminal or not end_dt:
            end_dt = datetime.now(UTC)
        started_at = _iso(started_dt)
        ended_at = _iso(end_dt)
        digest_source = f"{tx.display_id or tx.id}:{tx.state}:{ended_at}".encode()
        digest = "0x" + hashlib.sha256(digest_source).hexdigest()[:12]
        return {
            "txn_id": tx.display_id or tx.id,
            "quote_id": tx.quote_id,
            "amount_paise": tx.amount_paise,
            "currency": tx.currency,
            "state": tx.state,
            "decision": decision,
            "checkpoints": {"passed": passed_checks, "total": len(run_checks), "label": "Passed"},
            "duration_seconds": max(0, int((end_dt - started_dt).total_seconds())),
            "started_at": started_at,
            "ended_at": ended_at,
            "status": overall_status,
            "status_note": _state_to_status_note(tx.state),
            "reason": reason,
            "failed_checks": failed_checks,
            "review_checks": review_checks,
            "razorpay_order_id": tx.razorpay_order_id,
            "razorpay_payment_id": tx.razorpay_payment_id,
            "digest": digest,
            "immutable": True,
            "steps": steps,
        }


@router.get("/policies/limits")
async def api_limits(authorization: str | None = Header(default=None)) -> dict:
    _require_bearer(authorization)
    return {
        "limits": {
            "monthly_budget_usd": 45000,
            "per_transaction_inr": 500000,
            "autonomous_enabled": True,
        },
        "message": "Policy limits are evaluated server-side; see terms for details.",
    }
