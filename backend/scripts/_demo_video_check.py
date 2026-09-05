#!/usr/bin/env python3
"""Live video-demo checker: runs the PASS and FAIL(graceful) autorun scenarios
against the running server and prints every SSE event plus DB truth."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys

import httpx

BASE = "http://127.0.0.1:8000"


def _db(path="paari.db"):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def _latest_tx():
    c = _db()
    row = c.execute(
        "SELECT id, display_id, state, amount_paise, currency, razorpay_order_id, "
        "razorpay_payment_id, quote_id FROM transactions ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    c.close()
    return d


def _tx_extra(txn_id: str):
    c = _db()
    sessions = c.execute(
        "SELECT display_id, status, authorized_amount FROM payment_sessions WHERE transaction_id = :t",
        {"t": txn_id},
    ).fetchall()
    caps = c.execute(
        "SELECT display_id, action, used FROM payment_capabilities WHERE transaction_id = :t",
        {"t": txn_id},
    ).fetchall()
    pay_events = c.execute(
        "SELECT event_type FROM payment_events WHERE transaction_id = :t",
        {"t": txn_id},
    ).fetchall()
    audit = c.execute(
        "SELECT action, decision FROM audit_events WHERE payload_json LIKE :p "
        "ORDER BY created_at",
        {"p": f"%{txn_id}%"},
    ).fetchall()
    try:
        orders = c.execute(
            "SELECT name FROM shopify_orders WHERE transaction_id = :t",
            {"t": txn_id},
        ).fetchall()
    except Exception:
        orders = []
    c.close()
    return {
        "sessions": [tuple(s) for s in sessions],
        "capabilities": [tuple(s) for s in caps],
        "payment_events": [tuple(s) for s in pay_events],
        "audit": [tuple(a) for a in audit],
        "shopify_orders": [tuple(o) for o in orders],
    }


async def get_buyer_token() -> str:
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.post(
            f"{BASE}/api/auth/agent-token",
            json={"agent_type": "buyer", "agent_id": "BA-001"},
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def run_scenario(token: str, scenario: str, label: str) -> None:
    print("\n" + "=" * 72)
    print(f"  SCENARIO: {label}  (key: {scenario})")
    print("=" * 72)
    async with httpx.AsyncClient(timeout=120) as cli:
        async with cli.stream(
            "POST",
            f"{BASE}/api/agent/buyer/autorun",
            json={"scenario": scenario, "auto_escrow": True},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            print(f"  HTTP {resp.status_code}")
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    seq = ev.get("seq", "-")
                    typ = ev.get("type", "?")
                    text = (ev.get("text") or "").replace("\n", " ")[:150]
                    dec = ev.get("decision", "")
                    status = ev.get("status", "")
                    txn = ev.get("txn_id", "")
                    print(f"  [{typ:<16}] {text}")
                    if dec:
                        print(f"      decision={dec}  status={status}  txn={txn}")
    tx = _latest_tx()
    print("\n  -- DB TRUTH (latest transaction) --")
    if not tx:
        print("  none")
        return
    print(f"  display_id      : {tx['display_id']}")
    print(f"  state           : {tx['state']}")
    print(f"  amount          : Rs {tx['amount_paise']/100:.2f} {tx['currency']}")
    print(f"  razorpay order  : {tx['razorpay_order_id']}")
    print(f"  razorpay pay    : {tx['razorpay_payment_id']}")
    extra = _tx_extra(tx["id"])
    print(f"  sessions        : {extra['sessions']}")
    print(f"  capabilities    : {extra['capabilities']}")
    print(f"  payment_events  : {extra['payment_events']}")
    print(f"  shopify orders  : {extra['shopify_orders']}")
    decs = [a[1] for a in extra["audit"] if a[0] == "GOVERNANCE_DECISION"]
    chk = [a for a in extra["audit"] if a[0].startswith("GOVERNANCE_CHECK:")]
    print(f"  governance rows : decision={decs}  checks={len(chk)}")
    print("  ledger sample   :")
    for a in extra["audit"][:6]:
        print(f"      {a[0]}  ->  {a[1]}")


async def main() -> None:
    token = await get_buyer_token()
    print(f"buyer token acquired: {token[:18]}...")
    # 1) PASS
    await run_scenario(token, "snowboard-bundle-01", "PASS - happy path (ALLOW)")
    # 2) FAIL graceful
    await run_scenario(token, "payment-declined", "FAIL - payment declined (graceful)")
    # 3) also show the deny-leg proof (optional but free)
    await run_scenario(token, "deny-over-limit", "DENY - over limit (bonus proof)")


if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
