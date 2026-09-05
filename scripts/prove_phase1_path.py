"""Canonical Phase-1 proof: ALLOW / DENY / REVIEW + boundary robustness + credential layer.

Canonical path (ONLY governed authorize):
  POST /gateway/transactions (tx bound to ACCEPTED quote)
    -> POST /payments/create {transaction_id}
    -> POST /checkout/{display_id}/order {session_id} (bounded money touch)
    -> POST /payments/verify | payment.captured webhook

Prohibited in proof: POST /payments/simulate, un-governed authorize.

Run: python -m paari.seed && python scripts/prove_phase1_path.py
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from paari.authn.jwt_verifier import Identity
from paari.db.engine import get_session_maker
from paari.payment.service import get_payment_service
from paari.schemas.identity import AgentType


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    raise AssertionError(msg)


async def _make_quote_tx(
    session, tag: str, amount: int, buyer_id: str = "BA-001"
) -> tuple[str, str, str]:
    qid = f"Q-PROOF-{tag}-{secrets.token_hex(2).upper()}"
    txid = str(uuid.uuid4())
    did = f"TXN-PROOF-{tag}-{secrets.token_hex(2).upper()}"
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    await session.execute(
        text(
            "INSERT INTO quotes (id, transaction_id, merchant_id, amount_paise, expires_at, state) "
            "VALUES (:id, :tx, :mid, :amt, :exp, 'ACCEPTED')"
        ),
        {"id": qid, "tx": txid, "mid": "MER-001", "amt": amount, "exp": expires},
    )
    await session.execute(
        text(
            "INSERT INTO transactions (id, display_id, merchant_id, buyer_agent_id, "
            "merchant_agent_id, quote_id, amount_paise, currency, state, policy_version) "
            "VALUES (:id, :did, 'MER-001', :buyer, 'MA-001', :qid, :amt, 'INR', 'CREATED', 'v1')"
        ),
        {"id": txid, "did": did, "buyer": buyer_id, "qid": qid, "amt": amount},
    )
    await session.commit()
    return txid, did, qid


async def _make_quote_tx_with_cred(
    session, tag: str, amount: int, buyer_credential_json: str | None, buyer_id: str = "BA-001"
) -> tuple[str, str, str]:
    qid = f"Q-PROOF-{tag}-{secrets.token_hex(2).upper()}"
    txid = str(uuid.uuid4())
    did = f"TXN-PROOF-{tag}-{secrets.token_hex(2).upper()}"
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    await session.execute(
        text(
            "INSERT INTO quotes (id, transaction_id, merchant_id, amount_paise, expires_at, state) "
            "VALUES (:id, :tx, :mid, :amt, :exp, 'ACCEPTED')"
        ),
        {"id": qid, "tx": txid, "mid": "MER-001", "amt": amount, "exp": expires},
    )
    await session.execute(
        text(
            "INSERT INTO transactions (id, display_id, merchant_id, buyer_agent_id, "
            "merchant_agent_id, quote_id, amount_paise, currency, state, policy_version, buyer_credential_json) "
            "VALUES (:id, :did, 'MER-001', :buyer, 'MA-001', :qid, :amt, 'INR', 'CREATED', 'v1', :cred)"
        ),
        {
            "id": txid,
            "did": did,
            "buyer": buyer_id,
            "qid": qid,
            "amt": amount,
            "cred": buyer_credential_json,
        },
    )
    await session.commit()
    return txid, did, qid


async def _count(session, table: str, txid: str) -> int:
    row = (
        await session.execute(
            text(f"SELECT COUNT(*) AS c FROM {table} WHERE transaction_id = :t"),
            {"t": txid},
        )
    ).first()
    return int(row.c)


async def _ensure_review_actor(session) -> str:
    await session.execute(
        text(
            "INSERT OR IGNORE INTO users (id, display_id, name, status) "
            "VALUES ('USER-REVIEW', 'USER-REVIEW', 'Review Buyer', 'ACTIVE')"
        )
    )
    await session.execute(
        text(
            "INSERT OR REPLACE INTO user_policies (id, user_id, max_transaction_amount, "
            "daily_spending_limit, autonomous_payment, confirmation_threshold) "
            "VALUES ('UP-REVIEW', 'USER-REVIEW', 500000, 1000000, 0, 500000)"
        )
    )
    import json

    caps = json.dumps(
        [
            "catalog.read",
            "inventory.read",
            "product.read",
            "quote.request",
            "quote.accept",
            "payment.request",
            "payment.execute",
            "order.read",
        ]
    )
    await session.execute(
        text(
            "INSERT OR REPLACE INTO agents (id, merchant_id, agent_type, capabilities_json, "
            "display_id, owner_id, status) VALUES ('BA-REVIEW', NULL, 'BUYER', "
            ":caps, 'BA-REVIEW', 'USER-REVIEW', 'ACTIVE')"
        ),
        {"caps": caps},
    )
    await session.commit()
    return "BA-REVIEW"


async def _ensure_high_limit_buyer(session) -> str:
    await session.execute(
        text(
            "INSERT OR IGNORE INTO users (id, display_id, name, status) "
            "VALUES ('USER-HIGH', 'USER-HIGH', 'High Limit Buyer', 'ACTIVE')"
        )
    )
    await session.execute(
        text(
            "INSERT OR REPLACE INTO user_policies (id, user_id, max_transaction_amount, "
            "daily_spending_limit, autonomous_payment, confirmation_threshold) "
            "VALUES ('UP-HIGH', 'USER-HIGH', 100000000, 1000000000, 1, 100000000)"
        )
    )
    import json

    caps = json.dumps(
        [
            "catalog.read",
            "inventory.read",
            "product.read",
            "quote.request",
            "quote.accept",
            "payment.request",
            "payment.execute",
            "order.read",
        ]
    )
    await session.execute(
        text(
            "INSERT OR REPLACE INTO agents (id, merchant_id, agent_type, capabilities_json, "
            "display_id, owner_id, status) VALUES ('BA-HIGH', NULL, 'BUYER', "
            ":caps, 'BA-HIGH', 'USER-HIGH', 'ACTIVE')"
        ),
        {"caps": caps},
    )
    await session.commit()
    return "BA-HIGH"


async def main() -> None:
    maker = get_session_maker()
    service = get_payment_service()
    print("Phase-1 proof: governed HTTP path (service = handler logic)")

    async with maker() as s:
        reviewer = await _ensure_review_actor(s)

    # ── ALLOW ──────────────────────────────────────────────
    print("\n[1] ALLOW: authorize -> bounded order")
    async with maker() as s:
        txid, did, _ = await _make_quote_tx(s, "ALLOW", 120_000)
    res = await service.authorize_payment(did)
    if not res.authorized:
        _fail(f"ALLOW tx not authorized: {res.reason}")
    _ok(f"authorized session={res.session_display_id} amount={res.authorized_amount}")
    async with maker() as s:
        row = (
            await s.execute(
                text("SELECT status, authorized_amount FROM payment_sessions WHERE id = :i"),
                {"i": res.session_id},
            )
        ).first()
        if row is None or row.status != "ACTIVE":
            _fail("session not ACTIVE after ALLOW authorize")
        _ok("session ACTIVE")

    order = await service.create_razorpay_order(did, res.session_id or "")
    if not order.success:
        _fail(f"bounded order failed: {order.reason}")
    if not (order.order_id or "").startswith("order_"):
        _fail(f"unexpected order_id: {order.order_id}")
    async with maker() as s:
        txr = (
            await s.execute(
                text("SELECT razorpay_order_id, amount_paise FROM transactions WHERE id = :t"),
                {"t": txid},
            )
        ).first()
        if not txr.razorpay_order_id:
            _fail("razorpay_order_id not stored")
        if int(txr.amount_paise) != res.authorized_amount:
            _fail("stored amount != authorized_amount (unbounded!)")
    _ok(f"bounded order {order.order_id} amount==session.authorized_amount={res.authorized_amount}")

    # ── DENY ───────────────────────────────────────────────
    print("\n[2] DENY (over-limit): no session, no order")
    async with maker() as s:
        dtx, ddid, _ = await _make_quote_tx(s, "DENY", 900_000)
    dres = await service.authorize_payment(ddid)
    if dres.authorized:
        _fail("DENY tx was authorized")
    _ok(f"denied: {dres.reason}")
    async with maker() as s:
        if await _count(s, "payment_sessions", dtx) != 0:
            _fail("DENY minted a session")
        if await _count(s, "payment_capabilities", dtx) != 0:
            _fail("DENY minted a capability")
    _ok("no session/capability rows for DENY")
    adapter = await service.get_adapter()
    orig = adapter.create_order
    called = {"n": 0}

    async def _spy(**kw):
        called["n"] += 1
        return await orig(**kw)

    adapter.create_order = _spy  # type: ignore[method-assign]
    try:
        dorder = await service.create_razorpay_order(ddid, "forged-session-id")
    finally:
        adapter.create_order = orig  # type: ignore[method-assign]
    if dorder.success:
        _fail("DENY tx created an order")
    if called["n"] != 0:
        _fail("adapter called for DENY tx")
    _ok(f"no order for DENY (reason={dorder.reason}), adapter not called")

    # ── REVIEW ─────────────────────────────────────────────
    print("\n[3] REVIEW (autonomous disabled): no money call")
    async with maker() as s:
        rtx, rdid, _ = await _make_quote_tx(s, "REVIEW", 120_000, buyer_id=reviewer)
    rres = await service.authorize_payment(rdid)
    if rres.authorized:
        _fail("REVIEW tx was authorized")
    if "review" not in (rres.reason or "").lower():
        _fail(f"expected review_required, got: {rres.reason}")
    _ok(f"review_required: {rres.reason}")
    async with maker() as s:
        if await _count(s, "payment_sessions", rtx) != 0:
            _fail("REVIEW minted a session")
    adapter2 = await service.get_adapter()
    orig2 = adapter2.create_order
    called2 = {"n": 0}

    async def _spy2(**kw):
        called2["n"] += 1
        return await orig2(**kw)

    adapter2.create_order = _spy2  # type: ignore[method-assign]
    try:
        rorder = await service.create_razorpay_order(rdid, "forged-session-id")
    finally:
        adapter2.create_order = orig2  # type: ignore[method-assign]
    if rorder.success or called2["n"] != 0:
        _fail("REVIEW tx reached Razorpay")
    _ok("no money call for REVIEW, adapter not called")

    # ── Boundary robustness ────────────────────────────────
    print("\n[4] Boundary: forged / foreign / inactive / amount-mismatch")
    cases: list[tuple[str, str, str, str]] = []
    async with maker() as s:
        btx, bdid, _ = await _make_quote_tx(s, "BOUND", 120_000)
    bres = await service.authorize_payment(bdid)
    assert bres.authorized and bres.session_id
    good_sid = bres.session_id
    async with maker() as s:
        ftx, fdid, _ = await _make_quote_tx(s, "FOREIGN", 120_000)
    fres = await service.authorize_payment(fdid)
    assert fres.authorized and fres.session_id
    foreign_sid = fres.session_id or ""
    async with maker() as s:
        await s.execute(
            text("UPDATE payment_sessions SET status='COMPLETED' WHERE id = :i"),
            {"i": good_sid},
        )
        await s.commit()
    cases.append(("forged session_id", bdid, "PS-FORGED-DOES-NOT-EXIST", "session_not_found"))
    cases.append(("foreign-tx session_id", bdid, foreign_sid, "session_tx_mismatch"))
    cases.append(("inactive session", bdid, good_sid, "session_not_active"))
    async with maker() as s:
        mtx, mdid, _ = await _make_quote_tx(s, "MISMATCH", 120_000)
    mres = await service.authorize_payment(mdid)
    assert mres.authorized and mres.session_id
    async with maker() as s:
        await s.execute(
            text("UPDATE payment_sessions SET authorized_amount = 999999 WHERE id = :i"),
            {"i": mres.session_id},
        )
        await s.commit()
    cases.append(("amount mismatch", mdid, mres.session_id or "", "amount_mismatch"))

    for label, tx, sid, want in cases:
        probe = await service.get_adapter()
        witness = AsyncMock(wraps=probe.create_order)
        probe.create_order = witness  # type: ignore[method-assign]
        try:
            got = await service.create_razorpay_order(tx, sid)
        finally:
            pass
        if got.success:
            _fail(f"{label}: order succeeded unexpectedly")
        if (got.reason or "") != want:
            _fail(f"{label}: reason={got.reason!r} want={want!r}")
        if witness.await_count != 0:
            _fail(f"{label}: adapter create_order was called")
        _ok(f"{label} -> {want}, adapter not called")

    # ── Credential boundary ─────────────────────────────────
    print("\n[5] Credential boundary: layered buyer identity (Option 3)")

    async with maker() as s:
        high_buyer = await _ensure_high_limit_buyer(s)

    # Case 1: over threshold + no token -> REVIEW (config: deny=false)
    async with maker() as s:
        c1tx, c1did, _ = await _make_quote_tx_with_cred(
            s, "CREDSKIM", 200_000, None, buyer_id=high_buyer
        )
    with patch("paari.governance_engine.rules.buyer_credential.settings") as s_cred:
        s_cred.buyer_credential_required = False
        s_cred.buyer_credential_threshold_paise = 100_000
        s_cred.buyer_credential_deny_if_missing = False
        c1res = await service.authorize_payment(c1did)
    if c1res.authorized:
        _fail("over-threshold no-token was authorized (expected REVIEW)")
    if "review" not in (c1res.reason or "").lower():
        _fail(f"over-threshold no-token: expected review, got: {c1res.reason}")
    _ok(f"over-threshold no-token -> REVIEW (reason={c1res.reason})")

    # Case 2: over threshold + no token + deny=true -> DENY
    async with maker() as s:
        c2tx, c2did, _ = await _make_quote_tx_with_cred(
            s, "CREDDENY", 200_000, None, buyer_id=high_buyer
        )
    with patch("paari.governance_engine.rules.buyer_credential.settings") as s_cred:
        s_cred.buyer_credential_required = False
        s_cred.buyer_credential_threshold_paise = 100_000
        s_cred.buyer_credential_deny_if_missing = True
        c2res = await service.authorize_payment(c2did)
    if c2res.authorized:
        _fail("over-threshold no-token was authorized (expected DENY)")
    if "review" in (c2res.reason or "").lower():
        _fail(f"over-threshold no-token deny=true: expected DENY, got REVIEW")
    _ok(f"over-threshold no-token + deny=true -> DENY (reason={c2res.reason})")

    # Case 3: over threshold + valid buyer JWT -> ALLOW (mocked verify_token)
    async with maker() as s:
        c3tx, c3did, _ = await _make_quote_tx_with_cred(
            s, "CREDVALID", 200_000, "buyer.jwt.token", buyer_id=high_buyer
        )
    with (
        patch("paari.governance_engine.rules.buyer_credential.settings") as s_cred,
        patch("paari.governance_engine.rules.buyer_credential.verify_token") as vt,
    ):
        s_cred.buyer_credential_required = False
        s_cred.buyer_credential_threshold_paise = 100_000
        s_cred.buyer_credential_deny_if_missing = False
        vt.return_value = Identity(
            agent_id="BA-HIGH",
            agent_type=AgentType.BUYER,
            merchant_scope=None,
            capabilities=[],
            policy_version="v1",
            jti="proof-jti",
        )
        c3res = await service.authorize_payment(c3did)
    if not c3res.authorized:
        _fail(f"over-threshold valid JWT was not authorized: {c3res.reason}")
    _ok(f"over-threshold valid JWT -> ALLOW (session={c3res.session_display_id})")

    # Case 4: valid JWT but sub mismatch -> DENY
    async with maker() as s:
        c4tx, c4did, _ = await _make_quote_tx_with_cred(
            s, "CREDBAD", 200_000, "buyer.jwt.token", buyer_id=high_buyer
        )
    with (
        patch("paari.governance_engine.rules.buyer_credential.settings") as s_cred,
        patch("paari.governance_engine.rules.buyer_credential.verify_token") as vt,
    ):
        s_cred.buyer_credential_required = False
        s_cred.buyer_credential_threshold_paise = 100_000
        s_cred.buyer_credential_deny_if_missing = False
        vt.return_value = Identity(
            agent_id="BA-WRONG",
            agent_type=AgentType.BUYER,
            merchant_scope=None,
            capabilities=[],
            policy_version="v1",
            jti="proof-jti",
        )
        c4res = await service.authorize_payment(c4did)
    if c4res.authorized:
        _fail("JWT sub mismatch was authorized (expected DENY)")
    _ok(f"JWT sub mismatch -> DENY (reason={c4res.reason})")

    print(
        "\nPROOF COMPLETE: ALLOW bounded; DENY/REVIEW never reach Razorpay; 4 boundaries refused; 4 credential cases handled."
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"\nPROOF FAILED: {exc}")
        sys.exit(1)
