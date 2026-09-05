"""Live verification of the Governance Gateway (externally started server)."""
import sys, time, httpx, json, sqlite3, uuid
from datetime import UTC, datetime, timedelta

base = "http://127.0.0.1:8770"

def _wire_quote(tx_id: str, amount_paise: int) -> None:
    """Bind a fresh ACCEPTED quote to a transaction.

    QUOTE_VALIDATION enforces quote.transaction_id == tx.id, so a quote
    created for one transaction (e.g. seeded QUOTE-001 -> TXN-001) cannot be
    reused for another. Insert a quote owned by this tx and point the tx at it.
    """
    q_id = f"Q-AUDIT-{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO quotes (id, transaction_id, merchant_id, amount_paise, expires_at, state) "
        "VALUES (?, ?, 'MER-001', ?, ?, 'ACCEPTED')",
        (q_id, tx_id, amount_paise, (datetime.now(UTC) + timedelta(hours=1)).isoformat()),
    )
    db.execute("UPDATE transactions SET quote_id = ? WHERE id = ?", (q_id, tx_id))
    db.commit()
for _ in range(40):
    try:
        httpx.get(base + "/health", timeout=2); break
    except Exception: time.sleep(1)

c = httpx.Client(base_url=base, timeout=30)
db = sqlite3.connect("paari.db")
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS {name} {detail}")
    else: fail += 1; print(f"  FAIL {name} {detail}")

# 1. Evaluate seeded TXN-001 -> ALLOW with all checks visible
r = c.post("/gateway/governance/evaluate", json={"transaction_id": "TXN-001", "request_id": "REQ-AUDIT-1"})
d = r.json()
check("evaluate TXN-001 -> 200", r.status_code == 200, f"code={r.status_code}")
check("decision ALLOW", d.get("decision") == "ALLOW", str(d.get("decision")))
checks = {x["check"]: x for x in d.get("checks", [])}
check("8+ checks present", len(checks) >= 8, f"n={len(checks)}")  # 8 rules + PAARI_POLICY; session/capability intentionally deferred
check("policy delegated (PAARI_POLICY present)", "PAARI_POLICY" in checks, str(list(checks)[:12]))
check("risk check PASS with score", checks.get("RISK_CHECK", {}).get("status") == "PASS", str(checks.get("RISK_CHECK", {}).get("details", {}))[:120])
check("display_id in response", d.get("transaction_display_id") == "TXN-001", str(d.get("transaction_display_id")))

# 2. Create a new transaction (valid amount) -> evaluate -> authorize-payment
r2 = c.post("/gateway/transactions", json={
    "buyer_agent_display_id": "BA-001", "merchant_agent_display_id": "MA-001",
    "quote_id": "QUOTE-001", "amount_paise": 479900})
t = r2.json()
check("create transaction 200", r2.status_code == 200, f"code={r2.status_code}")
check("display_id generated", t.get("display_id", "").startswith("TXN-"), str(t))
new_did = t.get("display_id", "")
new_uuid = t.get("transaction_id", "")
_wire_quote(new_uuid, 479900)
r3 = c.post("/gateway/governance/evaluate", json={"transaction_id": new_did})
check("evaluate new tx ALLOW", r3.json().get("decision") == "ALLOW", str(r3.json().get("decision")))
r4 = c.post(f"/gateway/transactions/{new_did}/authorize-payment")
a = r4.json()
check("authorize-payment 200", r4.status_code == 200, f"code={r4.status_code}")
check("session+capability created", bool(a.get("payment_session_id")) and bool(a.get("capability_id")), str(a.get("payment_session_display_id")))
st = db.execute("SELECT state FROM transactions WHERE display_id=?", (new_did,)).fetchone()
check("tx state AUTHORIZED", st and st[0] == "AUTHORIZED", str(st))

# 3. Over-limit transaction (₹7,999) -> evaluate -> DENY, no Razorpay contact
r5 = c.post("/gateway/transactions", json={
    "buyer_agent_display_id": "BA-001", "merchant_agent_display_id": "MA-001",
    "quote_id": "QUOTE-001", "amount_paise": 799900})
bad_did = r5.json().get("display_id", "")
bad_uuid = r5.json().get("transaction_id", "")
_wire_quote(bad_uuid, 799900)
r6 = c.post("/gateway/governance/evaluate", json={"transaction_id": bad_did})
d6 = r6.json()
check("over-limit -> DENY", d6.get("decision") == "DENY", str(d6.get("decision")))
failed = [x["check"] for x in d6.get("failed_checks", [])]
check("USER_SPENDING_LIMIT fired", "USER_SPENDING_LIMIT" in failed, str(failed))

# 4. authorize-payment on the DENIED tx -> 409
r7 = c.post(f"/gateway/transactions/{bad_did}/authorize-payment")
check("authorize-payment blocked 409", r7.status_code == 409, f"code={r7.status_code}")

# 5. Audit trail: per-check + decision rows exist
n_check = db.execute("SELECT COUNT(*) FROM audit_events WHERE action LIKE 'GOVERNANCE_CHECK:%'").fetchone()[0]
n_dec = db.execute("SELECT COUNT(*) FROM audit_events WHERE action = 'GOVERNANCE_DECISION'").fetchone()[0]
check("per-check audit rows", n_check >= 22, f"n={n_check}")
check("decision audit rows", n_dec >= 3, f"n={n_dec}")

# 6. Illegal transition guard
from paari.governance_engine.state_machine import transition, IllegalTransitionError
import asyncio
async def _t():
    from paari.db.engine import get_session_maker
    maker = get_session_maker()
    async with maker() as s:
        row = db.execute("SELECT id FROM transactions WHERE display_id='TXN-001'").fetchone()
        await transition(s, row[0], "FULFILLED")  # CREATED-ish -> FULFILLED: illegal
try:
    asyncio.run(_t())
    check("illegal transition raises", False, "no exception")
except IllegalTransitionError:
    check("illegal transition raises", True)

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
