#!/usr/bin/env python3
"""Governance Demo — 3 scenarios proving the standalone gateway works.

Scenarios:
  1. ALLOW   TXN-001 (₹4,799, valid session/capability, risk LOW)
  2. DENY    doctored TXN-001 (amount raised to ₹7,999 > user limit ₹5,000)
  3. REVIEW  user_policy.autonomous_payment=0 → HUMAN_CONFIRMATION_REQUIRED

Run:
    python scripts/governance_demo.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

from paari.db.engine import get_session_maker, init_db
from paari.governance_engine.context import GovernanceContext
from paari.governance_engine.evaluator import get_governance_engine
from sqlalchemy import text


def _table() -> str:
    return "+" + "-" * 90 + "+"


def _row(*cols: str) -> str:
    return "|" + "|".join(f" {c:<28} " for c in cols) + "|"


async def _seed_demo(session) -> str:
    """Seed demo data and return the transaction id."""
    now = datetime.now(UTC)
    tx_id = "TXN-DEMO"
    await session.execute(text("DELETE FROM payment_capabilities WHERE transaction_id=:tid"), {"tid": tx_id})
    await session.execute(text("DELETE FROM payment_sessions WHERE transaction_id=:tid"), {"tid": tx_id})
    await session.execute(text("DELETE FROM quotes WHERE id='QUOTE-DEMO'"))
    await session.execute(text("DELETE FROM transactions WHERE id=:tid"), {"tid": tx_id})
    await session.execute(text("DELETE FROM user_policies WHERE id='UP-DEMO'"))
    await session.execute(text("DELETE FROM users WHERE id='USER-DEMO'"))
    await session.commit()

    await session.execute(
        text("INSERT INTO users (id, display_id, name, status) VALUES ('USER-DEMO', 'USER-DEMO', 'Demo Buyer', 'ACTIVE')")
    )
    await session.execute(
        text(
            "INSERT INTO user_policies (id, user_id, max_transaction_amount, daily_spending_limit, "
            " autonomous_payment, confirmation_threshold) "
            "VALUES ('UP-DEMO', 'USER-DEMO', :max, :daily, :auto, :threshold)"
        ),
        {"max": 500_000, "daily": 1_000_000, "auto": 1, "threshold": 500_000},
    )
    await session.execute(
        text(
            "INSERT INTO transactions (id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, "
            " quote_id, amount_paise, currency, state, policy_version) "
            "VALUES (:id, :did, 'MER-001', 'BA-001', 'MA-001', 'QUOTE-DEMO', :amt, 'INR', 'GOVERNANCE_PENDING', 'v1')"
        ),
        {"id": tx_id, "did": "TXN-DEMO", "amt": 479_900},
    )
    # Ensure risk engine doesn't block the baseline: raise merchant avg
    await session.execute(
        text("UPDATE merchants SET avg_transaction_paise=5000000 WHERE id='MER-001'"),
    )
    # Bind agent BA-001 to USER-DEMO so user_policy lookup resolves
    await session.execute(
        text("UPDATE agents SET owner_id='USER-DEMO' WHERE id='BA-001'"),
    )
    await session.execute(
        text(
            "INSERT INTO quotes (id, transaction_id, merchant_id, amount_paise, state, expires_at) "
            "VALUES ('QUOTE-DEMO', :tid, 'MER-001', 479900, 'ACCEPTED', :exp)"
        ),
        {"tid": tx_id, "exp": (now + timedelta(hours=1)).isoformat()},
    )
    await session.execute(
        text(
            "INSERT INTO payment_sessions (id, display_id, transaction_id, authorized_amount, currency, status, expires_at) "
            "VALUES ('PS-DEMO', 'PS-DEMO', :tid, 479900, 'INR', 'ACTIVE', :exp)"
        ),
        {"tid": tx_id, "exp": (now + timedelta(minutes=10)).isoformat()},
    )
    await session.execute(
        text(
            "INSERT INTO payment_capabilities (id, display_id, transaction_id, action, max_amount, usage, used) "
            "VALUES ('CAP-DEMO', 'CAP-DEMO', :tid, 'payment.execute', 479900, 'ONE_TIME', 0)"
        ),
        {"tid": tx_id},
    )
    await session.commit()
    return tx_id


async def run_scenario(name: str, modify_fn, tx_id: str, session) -> None:
    print(f"\n{'=' * 92}")
    print(f"  SCENARIO: {name}")
    print(f"{'=' * 92}")
    # Reset state and amount before each scenario
    await session.execute(
        text("UPDATE transactions SET state='GOVERNANCE_PENDING', amount_paise=479900 WHERE id=:tid"),
        {"tid": tx_id},
    )
    await session.execute(
        text("UPDATE quotes SET amount_paise=479900, state='ACCEPTED', expires_at=:exp WHERE id='QUOTE-DEMO'"),
        {"exp": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    )
    await session.execute(
        text("UPDATE payment_sessions SET authorized_amount=479900, status='ACTIVE', expires_at=:exp WHERE transaction_id=:tid"),
        {"tid": tx_id, "exp": (datetime.now(UTC) + timedelta(minutes=10)).isoformat()},
    )
    await session.execute(
        text("UPDATE payment_capabilities SET max_amount=479900, used=0 WHERE transaction_id=:tid"),
        {"tid": tx_id},
    )
    await session.commit()
    if modify_fn:
        await modify_fn(session)
        await session.commit()
    ctx = await GovernanceContext.load(session, tx_id, request_id=f"req-{name.lower()[:20]}")
    engine = get_governance_engine()
    decision = await engine.evaluate(ctx, session=session)
    await session.commit()
    print(f"  Transaction : {decision.transaction_display_id}  Amount: INR {ctx.transaction.amount_paise / 100:.2f}")
    print(f"  Decision    : {decision.decision}")
    print(f"  Policy ver  : {decision.policy_version}")
    print(f"\n  Per-check trace:")
    print(f"  {_table()}")
    print(f"  {'Check':<28} {'Status':<8} {'Reason code':<28} {'Details':<24}")
    print(f"  {_table()}")
    for c in decision.checks:
        detail = str(c.details)[:22] + "..." if len(str(c.details)) > 22 else str(c.details)
        print(f"  {c.check:<28} {c.status:<8} {c.reason_code:<28} {detail:<24}")
    print(f"  {_table()}")
    if decision.failed_checks:
        print(f"\n  Failed checks: {[c.reason_code for c in decision.failed_checks]}")
    if decision.review_checks:
        print(f"  Review checks: {[c.reason_code for c in decision.review_checks]}")
    print(f"\n  Razorpay was NOT contacted (governance gate only).")


async def main() -> int:
    await init_db()
    maker = get_session_maker()
    async with maker() as session:
        tx_id = await _seed_demo(session)

        # Scenario 1: ALLOW baseline
        async def noop(s):
            pass

        await run_scenario("ALLOW baseline (INR 4,799)", noop, tx_id, session)

        # Scenario 2: DENY — amount raised above user limit
        async def deny_amount(s):
            await s.execute(
                text("UPDATE transactions SET amount_paise=799900 WHERE id=:tid"),
                {"tid": tx_id},
            )
            await s.execute(
                text("UPDATE quotes SET amount_paise=799900 WHERE id='QUOTE-DEMO'"),
            )

        await run_scenario("DENY limit exceeded (INR 7,999 > INR 5,000)", deny_amount, tx_id, session)

        # Scenario 3: REVIEW — autonomous payment disabled
        async def review_autonomous(s):
            await s.execute(
                text("UPDATE user_policies SET autonomous_payment=0 WHERE user_id='USER-DEMO'"),
            )

        await run_scenario("REVIEW autonomous disabled", review_autonomous, tx_id, session)

    print(f"\n{'=' * 92}")
    print("  All 3 scenarios complete. Razorpay was NOT contacted in any of them.")
    print(f"{'=' * 92}\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
