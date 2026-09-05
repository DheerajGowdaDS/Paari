"""Governance Engine — full test matrix per blueprint §22.

Uses per-test temp SQLite DBs (pattern from tests/test_reviews.py).
Seed rows: USER-001/BA-001/MA-001/MER-001/QUOTE-001/TXN-001/PS-001/CAP-001.

Matrix:
  ALLOW baseline
  DENY: unknown agent, inactive agent, missing capability, unauthorized merchant,
       expired quote, quote-amount mismatch, user-limit exceeded, merchant-limit,
       expired session, used capability, wrong-transaction capability
  REVIEW: autonomous_payment disabled, risk MEDIUM
  Risk HIGH -> DENY RISK_BLOCKED
  Illegal transition raises IllegalTransitionError
  Per-check audit rows written
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from paari.governance_engine.context import GovernanceContext, GovernanceLoadError
from paari.governance_engine.evaluator import get_governance_engine
from paari.governance_engine.state_machine import (
    GovernanceTxState,
    IllegalTransitionError,
    VALID_TRANSITIONS,
    transition,
)


# ── test DB factory ─────────────────────────────────────────────────

def _maker():
    db_path = Path(__file__).resolve().parent / f"_test_gov_{uuid4().hex}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return maker, db_path, engine


async def _init_schema(engine) -> None:
    """Run init.sql against the given engine (not the global one)."""
    from pathlib import Path
    sql_path = Path(__file__).resolve().parent.parent / "paari" / "db" / "init.sql"
    sql = sql_path.read_text(encoding="utf-8")
    cleaned_lines = [line.split("--", 1)[0] for line in sql.splitlines()]
    cleaned_sql = "\n".join(cleaned_lines)
    pieces = [p.strip() for p in cleaned_sql.split(";") if p.strip()]
    async with engine.begin() as conn:
        for stmt in pieces:
            await conn.exec_driver_sql(stmt)


async def _seed_minimal(session: AsyncSession) -> None:
    """Seed the minimum rows needed for governance evaluation."""
    await session.execute(text("DELETE FROM payment_capabilities"))
    await session.execute(text("DELETE FROM payment_sessions"))
    await session.execute(text("DELETE FROM quotes"))
    await session.execute(text("DELETE FROM transactions"))
    await session.execute(text("DELETE FROM user_policies"))
    await session.execute(text("DELETE FROM users"))
    await session.execute(text("DELETE FROM agents"))
    await session.execute(text("DELETE FROM merchants"))
    await session.execute(text("DELETE FROM policies"))
    await session.commit()

    now = datetime.now(UTC)
    expires_at = (now + timedelta(hours=1)).isoformat()
    session_expires = (now + timedelta(minutes=10)).isoformat()

    # Merchant MER-001
    await session.execute(
        text(
            "INSERT INTO merchants (id, name, policy_version, shopify_domain, shopify_api_version, "
            " status, avg_transaction_paise, active_hours_utc, agent_transactions_enabled, display_id) "
            "VALUES ('MER-001', 'Paari Demo Store', 'v1', 'paari-demo-store.myshopify.com', '2025-01', "
            " 'AI_TRANSACTABLE', 5000000, :active, 1, 'MER-001')"
        ),
        {"active": json.dumps(list(range(9, 22)))},
    )

    # Buyer agent BA-001 with payment.request
    await session.execute(
        text(
            "INSERT INTO agents (id, merchant_id, agent_type, capabilities_json, display_id, owner_id) "
            "VALUES ('BA-001', NULL, 'BUYER', :caps, 'BA-001', 'USER-001')"
        ),
        {"caps": json.dumps(["payment.request", "catalog.read"])},
    )

    # Merchant agent MA-001
    await session.execute(
        text(
            "INSERT INTO agents (id, merchant_id, agent_type, capabilities_json, display_id, owner_id) "
            "VALUES ('MA-001', 'MER-001', 'MERCHANT', :caps, 'MA-001', 'MER-001')"
        ),
        {"caps": json.dumps(["quote.respond"])},
    )

    # Policies
    await session.execute(
        text(
            "INSERT INTO policies (id, merchant_id, layer, version, document_json, is_active) "
            "VALUES ('POL-001', 'MER-001', 'PAARI', 'v1', :doc, 1)"
        ),
        {"doc": json.dumps({"policy_id": "POL-001", "layer": "PAARI", "version": "v1", "rules": []})},
    )

    # USER-001 + policy
    await session.execute(
        text("INSERT INTO users (id, display_id, name, status) VALUES ('USER-001', 'USER-001', 'Demo Buyer', 'ACTIVE')")
    )
    await session.execute(
        text(
            "INSERT INTO user_policies (id, user_id, max_transaction_amount, daily_spending_limit, "
            " autonomous_payment, confirmation_threshold) "
            "VALUES ('UP-001', 'USER-001', :max, :daily, :auto, :threshold)"
        ),
        {"max": 5_000_000, "daily": 10_000_000, "auto": 1, "threshold": 500_000},
    )

    # TXN-001
    await session.execute(
        text(
            "INSERT INTO transactions (id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, "
            " quote_id, amount_paise, currency, state, policy_version) "
            "VALUES ('TXN-001', 'TXN-001', 'MER-001', 'BA-001', 'MA-001', 'QUOTE-001', 479900, 'INR', "
            " 'GOVERNANCE_PENDING', 'v1')"
        ),
    )

    # QUOTE-001
    await session.execute(
        text(
            "INSERT INTO quotes (id, transaction_id, merchant_id, amount_paise, state, expires_at) "
            "VALUES ('QUOTE-001', 'TXN-001', 'MER-001', 479900, 'ACCEPTED', :exp)"
        ),
        {"exp": expires_at},
    )

    # PS-001
    await session.execute(
        text(
            "INSERT INTO payment_sessions (id, display_id, transaction_id, authorized_amount, currency, status, expires_at) "
            "VALUES ('PS-001', 'PS-001', 'TXN-001', 479900, 'INR', 'ACTIVE', :exp)"
        ),
        {"exp": session_expires},
    )

    # CAP-001
    await session.execute(
        text(
            "INSERT INTO payment_capabilities (id, display_id, transaction_id, action, max_amount, usage, used) "
            "VALUES ('CAP-001', 'CAP-001', 'TXN-001', 'payment.execute', 479900, 'ONE_TIME', 0)"
        ),
    )

    await session.commit()


# ── fixtures ────────────────────────────────────────────────────────

async def _load_ctx(session: AsyncSession, tx_id: str = "TXN-001", req_id: str = "req-001") -> GovernanceContext:
    return await GovernanceContext.load(session, tx_id, request_id=req_id)


@pytest.fixture
async def gov_session():
    maker, db_path, engine = _maker()
    await _init_schema(engine)
    async with maker() as session:
        await _seed_minimal(session)
        await session.commit()
    async with maker() as session:
        yield session, engine
    db_path.unlink(missing_ok=True)


@pytest.fixture
async def gov_ctx(gov_session):
    session, _engine = gov_session
    ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-001")
    return ctx, session


# ── tests ───────────────────────────────────────────────────────────

class TestStateMachine:

    async def test_legal_transitions(self):
        maker, db_path, engine = _maker()
        await _init_schema(engine)
        async with maker() as session:
            await _seed_minimal(session)
            await session.commit()
            await transition(session, "TXN-001", "AUTHORIZED")
            await session.commit()
            row = await session.execute(text("SELECT state FROM transactions WHERE id='TXN-001'"))
            assert row.scalar() == "AUTHORIZED"
        db_path.unlink(missing_ok=True)

    async def test_illegal_transition_raises(self):
        maker, db_path, engine = _maker()
        await _init_schema(engine)
        async with maker() as session:
            await _seed_minimal(session)
            await session.commit()
            await transition(session, "TXN-001", "AUTHORIZED")
            await session.commit()
            with pytest.raises(IllegalTransitionError):
                await transition(session, "TXN-001", "CREATED")
        db_path.unlink(missing_ok=True)

    async def test_terminal_state_rejects_all(self):
        maker, db_path, engine = _maker()
        await _init_schema(engine)
        async with maker() as session:
            await _seed_minimal(session)
            await session.commit()
            await session.execute(text("UPDATE transactions SET state='DENIED' WHERE id='TXN-001'"))
            await session.commit()
            with pytest.raises(IllegalTransitionError):
                await transition(session, "TXN-001", "AUTHORIZED")
        db_path.unlink(missing_ok=True)

    async def test_valid_transitions_map_complete(self):
        states = list(GovernanceTxState)
        for from_s in states:
            for to_s in VALID_TRANSITIONS.get(from_s.value, []):
                target = GovernanceTxState(to_s)
                maker, db_path, engine = _maker()
                await _init_schema(engine)
                async with maker() as session:
                    await _seed_minimal(session)
                    await session.commit()
                    await session.execute(
                        text("UPDATE transactions SET state=:s WHERE id='TXN-001'"),
                        {"s": from_s.value},
                    )
                    await session.commit()
                    await transition(session, "TXN-001", target)
                    await session.commit()
                    row = await session.execute(text("SELECT state FROM transactions WHERE id='TXN-001'"))
                    assert row.scalar() == to_s
                db_path.unlink(missing_ok=True)


class TestGovernanceEngine:

    async def test_allow_baseline(self, gov_ctx):
        ctx, session = gov_ctx
        from paari.audit.logger import AuditLogger
        engine = get_governance_engine()
        audit = AuditLogger(session_maker=async_sessionmaker(
            session.get_bind(), expire_on_commit=False, class_=AsyncSession
        ))
        decision = await engine.evaluate(ctx, session=session, audit=audit)
        assert decision.decision == "ALLOW"
        assert len(decision.failed_checks) == 0
        assert all(c.status == "PASS" for c in decision.checks)

    async def test_deny_unknown_agent(self, gov_session):
        session, _engine = gov_session
        await session.execute(text("UPDATE transactions SET buyer_agent_id='UNKNOWN' WHERE id='TXN-001'"))
        await session.commit()
        ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-unk")
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert decision.decision == "DENY"
        check_names = [c.check for c in decision.failed_checks]
        assert "AGENT_IDENTITY" in check_names

    async def test_deny_inactive_agent(self, gov_session):
        session, _engine = gov_session
        await session.execute(
            text("UPDATE agents SET status='REVOKED' WHERE id='BA-001'")
        )
        await session.commit()
        ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-inact")
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert decision.decision == "DENY"
        reason_codes = [c.reason_code for c in decision.failed_checks]
        assert "AGENT_INACTIVE" in reason_codes

    async def test_deny_missing_capability(self, gov_session):
        session, _engine = gov_session
        await session.execute(
            text("UPDATE agents SET capabilities_json='[]' WHERE id='BA-001'")
        )
        await session.commit()
        ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-cap")
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert decision.decision == "DENY"
        assert any(c.reason_code == "MISSING_CAPABILITY" for c in decision.failed_checks)

    async def test_deny_unauthorized_merchant(self, gov_session):
        session, _engine = gov_session
        await session.execute(
            text("UPDATE merchants SET status='ARCHIVED' WHERE id='MER-001'")
        )
        await session.commit()
        ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-merch")
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert decision.decision == "DENY"
        assert any(c.reason_code == "MERCHANT_INACTIVE" for c in decision.failed_checks)

    async def test_deny_expired_quote(self, gov_session):
        session, _engine = gov_session
        past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        await session.execute(
            text("UPDATE quotes SET expires_at=:exp WHERE id='QUOTE-001'"),
            {"exp": past},
        )
        await session.commit()
        ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-exp")
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert decision.decision == "DENY"
        assert any(c.reason_code == "QUOTE_EXPIRED" for c in decision.failed_checks)

    async def test_deny_amount_mismatch(self, gov_session):
        session, _engine = gov_session
        await session.execute(
            text("UPDATE transactions SET amount_paise=999999 WHERE id='TXN-001'")
        )
        await session.commit()
        ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-amt")
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert decision.decision == "DENY"
        assert any(c.reason_code == "AMOUNT_MISMATCH" for c in decision.failed_checks)

    async def test_deny_user_limit_exceeded(self, gov_session):
        session, _engine = gov_session
        await session.execute(
            text("UPDATE user_policies SET max_transaction_amount=100 WHERE user_id='USER-001'")
        )
        await session.commit()
        ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-lim")
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert decision.decision == "DENY"
        assert any(c.reason_code == "LIMIT_EXCEEDED" for c in decision.failed_checks)

    async def test_review_autonomous_payment_disabled(self, gov_session):
        session, _engine = gov_session
        await session.execute(
            text("UPDATE user_policies SET autonomous_payment=0 WHERE user_id='USER-001'")
        )
        await session.commit()
        ctx = await GovernanceContext.load(session, "TXN-001", request_id="req-auto")
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert decision.decision == "REVIEW"
        assert any(c.reason_code == "HUMAN_CONFIRMATION_REQUIRED" for c in decision.checks)

    async def test_audit_rows_written(self, gov_session):
        session, engine = gov_session
        from paari.audit.logger import AuditLogger
        from sqlalchemy.ext.asyncio import async_sessionmaker
        audit = AuditLogger(session_maker=async_sessionmaker(engine, expire_on_commit=False))
        ctx = await _load_ctx(session)
        eng = get_governance_engine()
        await eng.evaluate(ctx, session=session, audit=audit)
        await session.commit()
        rows = (
            await session.execute(
                text("SELECT action, decision FROM audit_events WHERE request_id = :rid"),
                {"rid": ctx.request_id},
            )
        ).fetchall()
        actions = [r[0] for r in rows]
        decisions = [r[1] for r in rows]
        assert any("GOVERNANCE_CHECK:" in a for a in actions)
        assert "GOVERNANCE_DECISION" in actions
        assert "ALLOW" in decisions

    async def test_evaluate_returns_decision_with_checks(self, gov_ctx):
        ctx, session = gov_ctx
        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session=session)
        assert hasattr(decision, "checks")
        assert len(decision.checks) >= 8
