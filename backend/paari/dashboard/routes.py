"""Merchant operator dashboard routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import RedirectResponse

from paari.dashboard.session import (
    clear_session_cookie,
    create_session,
    optional_dashboard_session,
    set_session_cookie,
    verify_credentials,
)
from paari.dashboard.templates import render
from paari.review.service import REVIEW

_log = logging.getLogger("paari.dashboard")

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/login")
async def login_form(request: Request, error: str | None = None) -> str:
    return render("login.html", {"request": request, "error": error})


@router.post("/dashboard/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
) -> Response:
    if not verify_credentials(email, password):
        return RedirectResponse(
            url="/dashboard/login?error=invalid", status_code=status.HTTP_302_FOUND
        )
    token = create_session(email, merchant_id="merchant-demo-001")
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    set_session_cookie(response, token)
    return response


@router.get("/dashboard/logout")
async def logout(request: Request) -> Response:
    response = RedirectResponse(url="/dashboard/login", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(response)
    return response


def _require_session(session: dict | None) -> RedirectResponse | None:
    """Return a redirect-to-login response if the session is missing."""
    if session is None:
        return RedirectResponse(url="/dashboard/login", status_code=status.HTTP_302_FOUND)
    return None


def _fmt_ts(value) -> str:
    """Format a timestamp that may be a datetime or a string."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@router.get("/dashboard")
async def dashboard(request: Request, session=Depends(optional_dashboard_session)) -> Response:
    redirect = _require_session(session)
    if redirect is not None:
        return redirect
    records = await REVIEW.list_pending(merchant_id=session.get("merchant_id"))
    rows = [
        {
            "id": r.id,
            "transaction_id": r.transaction_id,
            "triggered_by": r.triggered_by,
            "reason": r.reason,
            "decision": r.decision,
            "sla_expires_at": _fmt_ts(r.sla_expires_at),
        }
        for r in records
    ]
    return render(
        "reviews.html", {"request": request, "session": session, "reviews": rows, "error": None}
    )


@router.post("/dashboard/reviews/{review_id}/approve")
async def approve_review(
    request: Request,
    review_id: str,
    note: str = Form(default=""),
    session=Depends(optional_dashboard_session),
) -> Response:
    redirect = _require_session(session)
    if redirect is not None:
        return redirect
    record = await REVIEW.decide(
        review_id=review_id,
        decision="APPROVE",
        decided_by=session.get("email", "operator"),
        note=note or None,
    )
    if record is None:
        return RedirectResponse(url="/dashboard?error=not_found", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@router.post("/dashboard/reviews/{review_id}/deny")
async def deny_review(
    request: Request,
    review_id: str,
    note: str = Form(default=""),
    session=Depends(optional_dashboard_session),
) -> Response:
    redirect = _require_session(session)
    if redirect is not None:
        return redirect
    record = await REVIEW.decide(
        review_id=review_id,
        decision="DENY",
        decided_by=session.get("email", "operator"),
        note=note or None,
    )
    if record is None:
        return RedirectResponse(url="/dashboard?error=not_found", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard/transactions/{display_id}")
async def transaction_detail(
    request: Request, display_id: str, session=Depends(optional_dashboard_session)
) -> Response:
    redirect = _require_session(session)
    if redirect is not None:
        return redirect
    from sqlalchemy import text
    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as s:
        tx = (
            await s.execute(
                text(
                    "SELECT id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, quote_id, amount_paise, currency, state, policy_version, razorpay_order_id, razorpay_payment_id, payment_session_id, created_at FROM transactions WHERE display_id=:d OR id=:d"
                ),
                {"d": display_id},
            )
        ).first()
        if tx is None:
            return render(
                "transaction.html",
                {
                    "request": request,
                    "session": session,
                    "error": f"Transaction not found: {display_id}",
                    "tx": None,
                },
            )
        sess = (
            await s.execute(
                text(
                    "SELECT id, display_id, authorized_amount, currency, status, expires_at FROM payment_sessions WHERE transaction_id=:t ORDER BY created_at DESC LIMIT 5"
                ),
                {"t": tx.id},
            )
        ).fetchall()
        caps = (
            await s.execute(
                text(
                    "SELECT id, display_id, action, max_amount, usage, used FROM payment_capabilities WHERE transaction_id=:t ORDER BY created_at DESC LIMIT 5"
                ),
                {"t": tx.id},
            )
        ).fetchall()
        pay_events = (
            await s.execute(
                text(
                    "SELECT id, event_type, payload_json, created_at FROM payment_events WHERE transaction_id=:t ORDER BY created_at"
                ),
                {"t": tx.id},
            )
        ).fetchall()
        audit = (
            await s.execute(
                text(
                    "SELECT id, request_id, action, decision, policy_version, payload_json, created_at FROM audit_events WHERE payload_json LIKE :pat ORDER BY created_at"
                ),
                {"pat": f"%{tx.display_id}%"},
            )
        ).fetchall()
        # governance checks are GOVERNANCE_CHECK:* rows for this tx
        checks = [r for r in audit if r.action.startswith("GOVERNANCE_CHECK:")]
        decision_row = next((r for r in audit if r.action == "GOVERNANCE_DECISION"), None)
        decision = decision_row.decision if decision_row else tx.state
        # quote info
        quote = None
        if tx.quote_id:
            quote = (
                await s.execute(
                    text("SELECT id, amount_paise, state FROM quotes WHERE id=:q"),
                    {"q": tx.quote_id},
                )
            ).first()

    return render(
        "transaction.html",
        {
            "request": request,
            "session": session,
            "tx": tx,
            "quote": quote,
            "sessions": sess,
            "capabilities": caps,
            "pay_events": pay_events,
            "checks": checks,
            "decision": decision,
            "audit": audit,
            "error": None,
        },
    )


@router.get("/dashboard/audit")
async def audit_view(request: Request, session=Depends(optional_dashboard_session)) -> Response:
    redirect = _require_session(session)
    if redirect is not None:
        return redirect
    from paari.audit.query import query_audit_events
    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session_db:
        rows = await query_audit_events(
            session_db, merchant_id=session.get("merchant_id"), limit=50
        )
    events = [
        {
            "id": r.id,
            "request_id": r.request_id,
            "action": r.action,
            "decision": r.decision,
            "policy_version": r.policy_version,
            "risk_score": r.risk_score,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return render("audit.html", {"request": request, "session": session, "events": events})
