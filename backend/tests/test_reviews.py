"""Step 14 validation: review service and SLA sweeper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from paari.review.service import ReviewService, _sla_deadline


def _service(sla_hours: int = 4) -> ReviewService:
    """A ReviewService backed by a fresh on-disk SQLite DB (test isolation).

    Each call gets a unique file so rows never leak between tests. The
    service ensures the reviews table exists on first use.
    """
    db_path = Path(__file__).resolve().parent / f"_test_reviews_{uuid4().hex}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    svc = ReviewService(session_maker=maker, sla_hours=sla_hours)
    svc._db_path = db_path  # type: ignore[attr-defined]
    return svc


async def test_create_review() -> None:
    svc = _service()
    record = await svc.create(
        merchant_id="merchant-demo-001",
        transaction_id="tx-1",
        triggered_by="POLICY",
        reason="over limit",
        pending_step={"tool_name": "request_quote"},
        gateway_context={"request_id": "req-1"},
    )
    assert record.id
    assert record.decision is None
    assert record.triggered_by == "POLICY"
    assert record.sla_expires_at > datetime.now(UTC)
    assert record.pending_step == {"tool_name": "request_quote"}


async def test_list_pending_returns_only_pending() -> None:
    svc = _service()
    r1 = await svc.create(merchant_id="m", transaction_id="t1", triggered_by="POLICY", reason="a")
    r2 = await svc.create(merchant_id="m", transaction_id="t2", triggered_by="RISK", reason="b")
    await svc.decide(r1.id, "APPROVE", decided_by="op")
    pending = await svc.list_pending(merchant_id="m")
    assert len(pending) == 1
    assert pending[0].id == r2.id


async def test_decide_approve() -> None:
    svc = _service()
    record = await svc.create(merchant_id="m", transaction_id="t", triggered_by="POLICY", reason="x")
    decided = await svc.decide(record.id, "APPROVE", decided_by="operator-1", note="ok")
    assert decided is not None
    assert decided.decision == "APPROVE"
    assert decided.decided_by == "operator-1"
    assert decided.note == "ok"
    assert decided.decided_at is not None


async def test_decide_already_decided_is_idempotent() -> None:
    svc = _service()
    record = await svc.create(merchant_id="m", transaction_id="t", triggered_by="POLICY", reason="x")
    await svc.decide(record.id, "DENY", decided_by="op")
    second = await svc.decide(record.id, "APPROVE", decided_by="other")
    assert second is not None
    assert second.decision == "DENY"  # unchanged


async def test_decide_unknown_review_returns_none() -> None:
    svc = _service()
    assert await svc.decide("nope", "APPROVE", decided_by="op") is None


async def test_auto_deny_expired() -> None:
    svc = _service(sla_hours=-1)  # SLA already in the past
    await svc.create(merchant_id="m", transaction_id="t", triggered_by="POLICY", reason="x")
    denied = await svc.auto_deny_expired()
    assert denied >= 1
    pending = await svc.list_pending(merchant_id="m")
    assert pending == []


def test_sla_deadline() -> None:
    before = datetime.now(UTC)
    deadline = _sla_deadline(4)
    after = datetime.now(UTC)
    assert before + timedelta(hours=4) <= deadline <= after + timedelta(hours=4)
