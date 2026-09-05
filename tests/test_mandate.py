"""Tests for mandate-based autonomous charging.

Rule matrix:
  no mandate_id       -> PASS / MANDATE_NOT_APPLICABLE
  mandate row missing -> FAIL / MANDATE_MISSING
  inactive            -> FAIL / MANDATE_INACTIVE
  autonomous off      -> FAIL / MANDATE_AUTONOMOUS_DISABLED
  owner mismatch      -> FAIL / MANDATE_OWNER_MISMATCH
  merchant blocked    -> FAIL / MANDATE_MERCHANT_BLOCKED
  amount over max     -> FAIL / MANDATE_AMOUNT_EXCEEDED
  daily over limit    -> FAIL / MANDATE_DAILY_EXCEEDED
  expired             -> FAIL / MANDATE_EXPIRED
  above review line   -> REVIEW / MANDATE_REVIEW_REQUIRED
  valid               -> PASS / MANDATE_VALID
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def _mandate(**over):
    base = {
        "id": "m1",
        "display_id": "MAND-001",
        "user_id": "USER-001",
        "provider": "RAZORPAY",
        "instrument_reference": "ref_1",
        "status": "ACTIVE",
        "max_per_transaction": 500_000,
        "daily_limit": 1_000_000,
        "allowed_merchants_json": json.dumps(["MER-001"]),
        "allowed_categories_json": json.dumps([]),
        "autonomous_enabled": 1,
        "requires_review_above": 300_000,
        "expires_at": None,
        "daily_used_paise": 0,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _ctx(
    amount=249_900, mandate_id="MAND-001", mandate=None, owner_id="USER-001", merchant_id="MER-001"
):
    tx = SimpleNamespace(
        id="tx1",
        display_id="TXN-1",
        merchant_id=merchant_id,
        amount_paise=amount,
        mandate_id=mandate_id,
    )
    agent = SimpleNamespace(
        id="BA-001", display_id="BA-001", owner_id=owner_id, capabilities=["payment.mandate_charge"]
    )
    merchant = SimpleNamespace(id=merchant_id, display_id=merchant_id)
    ctx = SimpleNamespace(agent=agent, transaction=tx, merchant=merchant, mandate=mandate)
    return ctx


def _check(ctx):
    from paari.governance_engine.rules.mandate import check

    return check(ctx)


class TestPassThrough:
    def test_no_mandate_id_passes(self):
        assert _check(_ctx(mandate_id=None)).reason_code == "MANDATE_NOT_APPLICABLE"

    def test_none_transaction_reviews(self):
        ctx = SimpleNamespace(agent=None, transaction=None, merchant=None, mandate=None)
        result = _check(ctx)
        assert (result.status, result.reason_code) == ("REVIEW", "MANDATE_OPTIONAL")


class TestFailures:
    def test_missing_row(self):
        result = _check(_ctx(mandate=None))
        assert (result.status, result.reason_code) == ("FAIL", "MANDATE_MISSING")

    def test_inactive(self):
        result = _check(_ctx(mandate=_mandate(status="REVOKED")))
        assert (result.status, result.reason_code) == ("FAIL", "MANDATE_INACTIVE")

    def test_autonomous_disabled(self):
        result = _check(_ctx(mandate=_mandate(autonomous_enabled=0)))
        assert (result.status, result.reason_code) == ("FAIL", "MANDATE_AUTONOMOUS_DISABLED")

    def test_owner_mismatch(self):
        result = _check(_ctx(mandate=_mandate(), owner_id="USER-999"))
        assert (result.status, result.reason_code) == ("FAIL", "MANDATE_OWNER_MISMATCH")

    def test_merchant_blocked(self):
        result = _check(_ctx(mandate=_mandate(), merchant_id="MER-999"))
        assert (result.status, result.reason_code) == ("FAIL", "MANDATE_MERCHANT_BLOCKED")

    def test_amount_exceeded(self):
        result = _check(_ctx(amount=700_000, mandate=_mandate()))
        assert (result.status, result.reason_code) == ("FAIL", "MANDATE_AMOUNT_EXCEEDED")

    def test_daily_exceeded(self):
        result = _check(_ctx(amount=200_000, mandate=_mandate(daily_used_paise=900_000)))
        assert (result.status, result.reason_code) == ("FAIL", "MANDATE_DAILY_EXCEEDED")

    def test_expired(self):
        result = _check(_ctx(mandate=_mandate(expires_at="2020-01-01T00:00:00+00:00")))
        assert (result.status, result.reason_code) == ("FAIL", "MANDATE_EXPIRED")


class TestReviewAndPass:
    def test_above_review_line(self):
        result = _check(_ctx(amount=400_000, mandate=_mandate()))
        assert (result.status, result.reason_code) == ("REVIEW", "MANDATE_REVIEW_REQUIRED")

    def test_valid(self):
        result = _check(_ctx(mandate=_mandate()))
        assert (result.status, result.reason_code) == ("PASS", "MANDATE_VALID")
        assert result.details["mandate_policy"] == "LOADED"

    def test_boundary_amount_passes(self):
        result = _check(_ctx(amount=300_000, mandate=_mandate()))
        assert result.status == "PASS"

    def test_empty_allow_list_permits_any_merchant(self):
        result = _check(_ctx(mandate=_mandate(allowed_merchants_json="[]"), merchant_id="MER-999"))
        assert result.status == "PASS"


class TestPipeline:
    def test_mandate_in_pipeline_after_user_spending(self):
        from paari.governance_engine.rules import RULE_PIPELINE
        from paari.governance_engine.rules import autonomous_payment as ap_mod
        from paari.governance_engine.rules import mandate as mandate_mod
        from paari.governance_engine.rules import user_spending as us_mod

        names = [f.__module__ for f in RULE_PIPELINE]
        assert mandate_mod.__name__ in names
        assert names.index(mandate_mod.__name__) > names.index(us_mod.__name__)
        assert names.index(mandate_mod.__name__) < names.index(ap_mod.__name__)


class TestCapability:
    def test_enum_value(self):
        from paari.schemas.capability import Capability

        assert Capability.PAYMENT_MANDATE_CHARGE.value == "payment.mandate_charge"

    def test_agent_authorization_accepts_mandate_cap(self):
        from paari.governance_engine.rules.agent_authorization import check

        agent = SimpleNamespace(
            id="BA-001", display_id="BA-001", capabilities=["payment.mandate_charge"]
        )
        tx = SimpleNamespace(mandate_id="MAND-001")
        result = check(SimpleNamespace(agent=agent, transaction=tx))
        assert (result.status, result.reason_code) == ("PASS", "CAPABILITY_PRESENT_MANDATE")

    def test_agent_authorization_still_requires_request_without_mandate(self):
        from paari.governance_engine.rules.agent_authorization import check

        agent = SimpleNamespace(
            id="BA-001", display_id="BA-001", capabilities=["payment.mandate_charge"]
        )
        tx = SimpleNamespace(mandate_id=None)
        result = check(SimpleNamespace(agent=agent, transaction=tx))
        assert (result.status, result.reason_code) == ("FAIL", "MISSING_CAPABILITY")

    def test_agent_authorization_human_path_unchanged(self):
        from paari.governance_engine.rules.agent_authorization import check

        agent = SimpleNamespace(id="BA-001", display_id="BA-001", capabilities=["payment.request"])
        tx = SimpleNamespace(mandate_id=None)
        result = check(SimpleNamespace(agent=agent, transaction=tx))
        assert (result.status, result.reason_code) == ("PASS", "CAPABILITY_PRESENT")


class TestProviders:
    @pytest.mark.asyncio
    async def test_stub_approves(self):
        from paari.tools.adapters.razorpay_stub import RazorpyStubAdapter

        out = await RazorpyStubAdapter(webhook_secret="s").charge_mandate("ref", 249_900)
        assert out["success"] is True and out["status"] == "captured"

    @pytest.mark.asyncio
    async def test_stub_declines_99(self):
        from paari.tools.adapters.razorpay_stub import RazorpyStubAdapter

        out = await RazorpyStubAdapter(webhook_secret="s").charge_mandate("ref", 249_999)
        assert out["success"] is False and out["status"] == "failed"

    @pytest.mark.asyncio
    async def test_live_not_integrated(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter("k", "s", "w")
        with pytest.raises(NotImplementedError):
            await adapter.charge_mandate("ref", 100)


class TestSeed:
    def test_mandate_seeded(self):
        import sqlite3

        conn = sqlite3.connect("paari.db")
        try:
            row = conn.execute(
                "SELECT status, max_per_transaction FROM mandates WHERE display_id='MAND-001'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None and row[0] == "ACTIVE" and int(row[1]) == 500_000

    def test_buyer_has_mandate_grant(self):
        import json as _json
        import sqlite3

        conn = sqlite3.connect("paari.db")
        try:
            caps = conn.execute(
                "SELECT capabilities_json FROM agents WHERE id='BA-001'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert "payment.mandate_charge" in _json.loads(caps)


class TestMandateChargeE2E:
    async def _setup_run(self, session, tag, amount, mandate_id="MAND-TEST"):
        import secrets as _secrets
        import uuid as _uuid
        from datetime import UTC as _UTC
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        from sqlalchemy import text as _text

        await session.execute(
            _text(
                "INSERT OR IGNORE INTO merchants (id, display_id, name, policy_version, status, "
                " agent_transactions_enabled, avg_transaction_paise, autonomous_limit_paise,"
                " active_hours_utc) "
                "VALUES ('MER-MANDATE','MER-MANDATE','Mandate Demo','v1','AI_TRANSACTABLE',"
                "1,250000,2000000,:h)"
            ),
            {"h": json.dumps(list(range(0, 24)))},
        )
        await session.execute(
            _text(
                "INSERT OR IGNORE INTO mandates (id, display_id, user_id, provider, instrument_reference,"
                " status, max_per_transaction, daily_limit, allowed_merchants_json,"
                " allowed_categories_json, autonomous_enabled, requires_review_above) "
                "VALUES (:id,:d,'USER-001','RAZORPAY','ref_e2e','ACTIVE',500000,1000000,:m,:c,1,300000)"
            ),
            {
                "id": mandate_id,
                "d": mandate_id,
                "m": json.dumps(["MER-MANDATE"]),
                "c": json.dumps([]),
            },
        )
        txid = str(_uuid.uuid4())
        did = f"TXN-MANDATE-{tag}-{_secrets.token_hex(2).upper()}"
        qid = f"Q-MANDATE-{tag}-{_secrets.token_hex(2).upper()}"
        exp = (_dt.now(_UTC) + _td(hours=1)).isoformat()
        await session.execute(
            _text(
                "INSERT INTO quotes (id, transaction_id, merchant_id, amount_paise, expires_at, state) "
                "VALUES (:id,:tx,'MER-MANDATE',:amt,:exp,'ACCEPTED')"
            ),
            {"id": qid, "tx": txid, "amt": amount, "exp": exp},
        )
        await session.execute(
            _text(
                "INSERT INTO transactions (id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, "
                " quote_id, amount_paise, currency, state, policy_version, mandate_id) "
                "VALUES (:id,:did,'MER-MANDATE','BA-001','MA-001',:qid,:amt,'INR','CREATED','v1',:mid)"
            ),
            {"id": txid, "did": did, "qid": qid, "amt": amount, "mid": mandate_id},
        )
        await session.commit()
        return txid, did

    async def _teardown_run(self, session, txid, mandate_id="MAND-TEST"):
        from sqlalchemy import text as _text

        await session.execute(
            _text("DELETE FROM payment_capabilities WHERE transaction_id=:t"), {"t": txid}
        )
        await session.execute(
            _text("DELETE FROM payment_sessions WHERE transaction_id=:t"), {"t": txid}
        )
        await session.execute(
            _text("DELETE FROM payment_events WHERE transaction_id=:t"), {"t": txid}
        )
        await session.execute(
            _text("DELETE FROM idempotency_keys WHERE key LIKE :k"),
            {"k": f"mandate-charge:{txid}%"},
        )
        await session.execute(_text("DELETE FROM quotes WHERE transaction_id=:t"), {"t": txid})
        await session.execute(_text("DELETE FROM transactions WHERE id=:t"), {"t": txid})
        await session.execute(
            _text("DELETE FROM mandate_daily_usage WHERE mandate_id=:m"), {"m": mandate_id}
        )
        await session.execute(_text("DELETE FROM mandates WHERE id=:m"), {"m": mandate_id})
        await session.commit()

    @pytest.mark.asyncio
    async def test_full_charge_and_replay(self, monkeypatch):
        from paari.config import settings as _settings

        monkeypatch.setattr(_settings, "razorpay_mode", "stub")
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import text as _text

        from paari.db.engine import get_session_maker
        from paari.main import app

        maker = get_session_maker()
        async with maker() as session:
            txid, did = await self._setup_run(session, "OK", 249_900)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = await client.post(
                    "/payments/mandate-charge",
                    json={"transaction_id": did, "mandate_id": "MAND-TEST"},
                )
                assert first.status_code == 200, first.text
                body = first.json()
                assert body["success"] is True and body["status"] == "VERIFIED"
                second = await client.post(
                    "/payments/mandate-charge",
                    json={"transaction_id": did, "mandate_id": "MAND-TEST"},
                )
                assert second.status_code == 200
                assert second.json()["payment_id"] == body["payment_id"]
            async with maker() as session:
                state = (
                    await session.execute(
                        _text("SELECT state FROM transactions WHERE id=:t"), {"t": txid}
                    )
                ).first()
                assert state.state == "COMPLETED"
                used = (
                    await session.execute(
                        _text(
                            "SELECT used_paise FROM mandate_daily_usage WHERE mandate_id='MAND-TEST'"
                        )
                    )
                ).first()
                assert int(used.used_paise) == 249_900
        finally:
            async with maker() as session:
                await self._teardown_run(session, txid)

    @pytest.mark.asyncio
    async def test_decline_marks_failed_no_fulfill(self, monkeypatch):
        from paari.config import settings as _settings

        monkeypatch.setattr(_settings, "razorpay_mode", "stub")
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import text as _text

        from paari.db.engine import get_session_maker
        from paari.main import app

        maker = get_session_maker()
        async with maker() as session:
            txid, did = await self._setup_run(session, "NO", 249_999)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/payments/mandate-charge",
                    json={"transaction_id": did, "mandate_id": "MAND-TEST"},
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["success"] is False
            async with maker() as session:
                state = (
                    await session.execute(
                        _text("SELECT state FROM transactions WHERE id=:t"), {"t": txid}
                    )
                ).first()
                assert state.state == "PAYMENT_FAILED"
        finally:
            async with maker() as session:
                await self._teardown_run(session, txid)

    @pytest.mark.asyncio
    async def test_review_amount_blocked(self):
        from httpx import ASGITransport, AsyncClient

        from paari.db.engine import get_session_maker
        from paari.main import app

        maker = get_session_maker()
        async with maker() as session:
            txid, did = await self._setup_run(session, "RV", 400_000)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/payments/mandate-charge",
                    json={"transaction_id": did, "mandate_id": "MAND-TEST"},
                )
                assert resp.status_code == 403, resp.text
        finally:
            async with maker() as session:
                await self._teardown_run(session, txid)

    @pytest.mark.asyncio
    async def test_enroll_and_validation(self):
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import text as _text

        from paari.db.engine import get_session_maker
        from paari.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            bad = await client.post(
                "/mandates/enroll",
                json={
                    "user_id": "USER-001",
                    "instrument_reference": "ref_x",
                    "max_per_transaction": 999,
                    "daily_limit": 100,
                    "allowed_merchants": [],
                },
            )
            assert bad.status_code == 400
            missing = await client.post(
                "/mandates/enroll",
                json={
                    "user_id": "USER-NOBODY",
                    "instrument_reference": "ref_x",
                    "max_per_transaction": 100,
                    "daily_limit": 200,
                    "allowed_merchants": [],
                },
            )
            assert missing.status_code == 404
            ok = await client.post(
                "/mandates/enroll",
                json={
                    "user_id": "USER-001",
                    "instrument_reference": "ref_e2e_enroll",
                    "max_per_transaction": 5000,
                    "daily_limit": 10000,
                    "allowed_merchants": ["MER-001"],
                },
            )
            assert ok.status_code == 200, ok.text
            mid = ok.json()["mandate_id"]
            detail = await client.get(f"/mandates/{mid}")
            assert detail.status_code == 200
            assert detail.json()["used_today_paise"] == 0
        maker = get_session_maker()
        async with maker() as session:
            await session.execute(_text("DELETE FROM mandates WHERE id=:m"), {"m": mid})
            await session.commit()

    @pytest.mark.asyncio
    async def test_enroll_writes_mandate_audit(self):
        """Blueprint Phase 13: enrollment writes a MANDATE_CREATED audit row."""
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import text as _text

        from paari.db.engine import get_session_maker
        from paari.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ok = await client.post(
                "/mandates/enroll",
                json={
                    "user_id": "USER-001",
                    "instrument_reference": "ref_audit_enroll",
                    "max_per_transaction": 5000,
                    "daily_limit": 10000,
                    "allowed_merchants": ["MER-001"],
                },
            )
            assert ok.status_code == 200, ok.text
            display_id = ok.json()["display_id"]
        maker = get_session_maker()
        try:
            async with maker() as session:
                row = (
                    await session.execute(
                        _text(
                            "SELECT 1 FROM audit_events WHERE action='MANDATE_CREATED' "
                            "AND payload_json LIKE :pat"
                        ),
                        {"pat": f"%{display_id}%"},
                    )
                ).first()
                assert row is not None, f"MANDATE_CREATED audit row missing for {display_id}"
        finally:
            async with maker() as session:
                await session.execute(
                    _text("DELETE FROM mandates WHERE display_id=:d"), {"d": display_id}
                )
                await session.commit()

    @pytest.mark.asyncio
    async def test_single_authorize_no_orphaned_rows(self, monkeypatch):
        """P1-1: exactly one authorize -> one session + one capability (no orphans)."""
        from paari.config import settings as _settings

        monkeypatch.setattr(_settings, "razorpay_mode", "stub")
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import text as _text

        from paari.db.engine import get_session_maker
        from paari.main import app

        maker = get_session_maker()
        async with maker() as session:
            txid, did = await self._setup_run(session, "ORPHAN", 249_900)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/payments/mandate-charge",
                    json={"transaction_id": did, "mandate_id": "MAND-TEST"},
                )
                assert resp.status_code == 200, resp.text
            async with maker() as session:
                sessions = (
                    await session.execute(
                        _text(
                            "SELECT COUNT(*) AS n FROM payment_sessions WHERE transaction_id=:t"
                        ),
                        {"t": txid},
                    )
                ).first()
                caps = (
                    await session.execute(
                        _text(
                            "SELECT COUNT(*) AS n FROM payment_capabilities "
                            "WHERE transaction_id=:t"
                        ),
                        {"t": txid},
                    )
                ).first()
                assert sessions.n == 1, "single authorize must create one session"
                assert caps.n == 1, "single authorize must create one one-time capability"
        finally:
            async with maker() as session:
                await self._teardown_run(session, txid)

    @pytest.mark.asyncio
    async def test_fresh_key_cannot_double_charge(self, monkeypatch):
        """P1-2/Phase 8: a second charge under a NEW key is rejected (409)."""
        from paari.config import settings as _settings

        monkeypatch.setattr(_settings, "razorpay_mode", "stub")
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import text as _text

        from paari.db.engine import get_session_maker
        from paari.main import app

        maker = get_session_maker()
        async with maker() as session:
            txid, did = await self._setup_run(session, "2CHG", 249_900)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = await client.post(
                    "/payments/mandate-charge",
                    json={"transaction_id": did, "mandate_id": "MAND-TEST"},
                )
                assert first.status_code == 200, first.text
                second = await client.post(
                    "/payments/mandate-charge",
                    json={
                        "transaction_id": did,
                        "mandate_id": "MAND-TEST",
                        "idempotency_key": f"alt-key-{did}",
                    },
                )
                assert second.status_code == 409, second.text
                assert "tx_not_chargeable" in second.text
            async with maker() as session:
                used = (
                    await session.execute(
                        _text(
                            "SELECT used_paise FROM mandate_daily_usage "
                            "WHERE mandate_id='MAND-TEST'"
                        )
                    )
                ).first()
                assert int(used.used_paise) == 249_900, "only one charge may accrue usage"
                verified = (
                    await session.execute(
                        _text(
                            "SELECT COUNT(*) AS n FROM payment_events "
                            "WHERE transaction_id=:t AND event_type='payment.verified'"
                        ),
                        {"t": txid},
                    )
                ).first()
                assert verified.n == 1, "one charge -> one verified event"
        finally:
            async with maker() as session:
                await self._teardown_run(session, txid)

    @pytest.mark.asyncio
    async def test_decline_consumes_no_daily_usage(self, monkeypatch):
        """P2-5: a declined charge consumes no daily budget and expires the session."""
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from paari.config import settings as _settings

        monkeypatch.setattr(_settings, "razorpay_mode", "stub")
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import text as _text

        from paari.db.engine import get_session_maker
        from paari.main import app

        maker = get_session_maker()
        async with maker() as session:
            txid, did = await self._setup_run(session, "DECL", 249_999)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/payments/mandate-charge",
                    json={"transaction_id": did, "mandate_id": "MAND-TEST"},
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["success"] is False
            day = _dt.now(_UTC).strftime("%Y-%m-%d")
            async with maker() as session:
                state = (
                    await session.execute(
                        _text("SELECT state FROM transactions WHERE id=:t"), {"t": txid}
                    )
                ).first()
                assert state.state == "PAYMENT_FAILED"
                usage = (
                    await session.execute(
                        _text(
                            "SELECT used_paise FROM mandate_daily_usage "
                            "WHERE mandate_id='MAND-TEST' AND day=:d"
                        ),
                        {"d": day},
                    )
                ).first()
                assert usage is None, "decline must not consume the daily budget"
                sess = (
                    await session.execute(
                        _text(
                            "SELECT status FROM payment_sessions WHERE transaction_id=:t"
                        ),
                        {"t": txid},
                    )
                ).first()
                assert sess.status == "FAILED", "declined session must be expired"
        finally:
            async with maker() as session:
                await self._teardown_run(session, txid)

    @pytest.mark.asyncio
    async def test_mandate_charge_audit_events_written(self, monkeypatch):
        """Blueprint Phase 13: the charge path writes MANDATE_* audit events."""
        from paari.config import settings as _settings

        monkeypatch.setattr(_settings, "razorpay_mode", "stub")
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import text as _text

        from paari.db.engine import get_session_maker
        from paari.main import app

        maker = get_session_maker()
        async with maker() as session:
            txid, did = await self._setup_run(session, "AUD", 249_900)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/payments/mandate-charge",
                    json={"transaction_id": did, "mandate_id": "MAND-TEST"},
                )
                assert resp.status_code == 200, resp.text
            expected = {
                "MANDATE_CHARGE_REQUESTED",
                "CHARGE_AUTHORIZED",
                "RAZORPAY_CHARGE_REQUESTED",
                "RAZORPAY_PAYMENT_CONFIRMED",
            }
            async with maker() as session:
                rows = (
                    await session.execute(
                        _text(
                            "SELECT DISTINCT action FROM audit_events "
                            "WHERE payload_json LIKE :pat"
                        ),
                        {"pat": "%MAND-TEST%"},
                    )
                ).all()
                actions = {r.action for r in rows}
                missing = expected - actions
                assert not missing, f"missing mandate audit events: {missing}"
        finally:
            async with maker() as session:
                await self._teardown_run(session, txid)


class TestEndpointSchemas:
    def test_extra_forbidden(self):
        from paari.api.mandates import EnrollMandateRequest
        from paari.api.payments import MandateChargeRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EnrollMandateRequest(
                user_id="u",
                instrument_reference="r",
                max_per_transaction=1,
                daily_limit=2,
                bogus_field="x",
            )
        with pytest.raises(ValidationError):
            MandateChargeRequest(
                transaction_id="t", authorization_id="a", mandate_id="m", bogus_field="x"
            )
