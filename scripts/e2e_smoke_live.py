"""Full E2E smoke test — live mode against paari-demo-store.myshopify.com."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def test(name: str, fn) -> None:
    global PASS, FAIL
    try:
        result = fn()
        if result is False:
            FAIL += 1
            print(f"  FAIL  {name}")
        else:
            PASS += 1
            print(f"  OK    {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: {e}")


def get(path: str, headers: dict = None) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", headers=headers or {})
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())


def post(path: str, data: dict, headers: dict = None) -> dict | int:
    body = json.dumps(data).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=h, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code


def main() -> None:
    global PASS, FAIL

    print("=" * 60)
    print("E2E SMOKE TEST — LIVE MODE")
    print("=" * 60)
    print()

    # ── 1. Health ────────────────────────────────────────────────────
    print("1. Health check")
    test("GET /api/v1/health returns live mode", lambda: get("/api/v1/health")["adapter_mode"] == "live")
    test("DB connected", lambda: get("/api/v1/health")["db_connected"] is True)
    test("Store context fresh", lambda: get("/api/v1/health")["store_context_fresh"] is True)
    print()

    # ── 2. Agent Card ────────────────────────────────────────────────
    print("2. Agent card (discovery)")
    card = get("/api/v1/merchants/MER-001/agent-card")
    test("Status is AI_TRANSACTABLE", lambda: card["status"] == "AI_TRANSACTABLE")
    test("Currency is INR", lambda: card["currency"] == "INR")
    test("Autonomous limit is 5000000", lambda: card["restrictions"]["max_autonomous_transaction"] == 5000000)
    test("Has capabilities", lambda: len(card["capabilities"]) >= 5)
    test("Has policies", lambda: "return_window_days" in card["policies"])
    test("Has endpoints", lambda: "negotiate" in card["endpoints"])
    print()

    # ── 3. JWT Token ─────────────────────────────────────────────────
    print("3. JWT token issuance")
    token_resp = post("/auth/agent-token", {"agent_id": "buyer-agent-001", "agent_type": "BUYER"})
    token = token_resp["access_token"]
    test("Token issued", lambda: len(token) > 50)
    test("Token type is Bearer", lambda: token_resp["token_type"] == "Bearer")
    print()

    # ── 4. Agent /run — Search Products ──────────────────────────────
    print("4. Agent /run — search for snowboards")
    result = post("/agent/run", {"buyer_request": "search for snowboards"}, {"Authorization": f"Bearer {token}"})
    test("Status is completed", lambda: result["status"] == "completed")
    test("Transaction ID present", lambda: result.get("transaction_id") is not None)
    test("Tool call executed", lambda: len(result.get("tool_results", [])) >= 1)
    tool_result = result["tool_results"][0] if result.get("tool_results") else {}
    test("Source is shopify_live", lambda: tool_result.get("payload", {}).get("source") == "shopify_live")
    print()

    # ── 5. Webhook HMAC ──────────────────────────────────────────────
    print("5. Webhook HMAC verification")
    import base64, hashlib, hmac as hmac_mod
    # Known test vector for HMAC self-check only — NOT a real credential.
    secret = b"0123456789abcdef0123456789abcdef"  # 32-byte dummy, not a real Shopify secret
    body = json.dumps({"id": 99999, "financial_status": "paid", "note": "", "tags": []}).encode()
    sig = base64.b64encode(hmac_mod.new(secret, body, hashlib.sha256).digest()).decode()

    # Valid HMAC
    test("Valid HMAC accepted", lambda: post("/webhooks/shopify/orders_create",
        json.loads(body),
        {"X-Shopify-Hmac-SHA256": sig, "X-Shopify-Webhook-Id": "smoke-test-001"}) == {"status": "ok"})

    # Duplicate webhook deduped
    test("Duplicate webhook deduped", lambda: "duplicate" in str(post("/webhooks/shopify/orders_create",
        json.loads(body),
        {"X-Shopify-Hmac-SHA256": sig, "X-Shopify-Webhook-Id": "smoke-test-001"})))

    # Bad HMAC rejected
    test("Bad HMAC rejected (401)", lambda: post("/webhooks/shopify/orders_create",
        json.loads(body),
        {"X-Shopify-Hmac-SHA256": "badsig", "X-Shopify-Webhook-Id": "smoke-test-002"}) == 401)

    # Missing HMAC rejected (live mode)
    test("Missing HMAC rejected (401)", lambda: post("/webhooks/shopify/orders_create",
        json.loads(body), {"X-Shopify-Webhook-Id": "smoke-test-003"}) == 401)
    print()

    # ── 6. Tool Health ───────────────────────────────────────────────
    print("6. Tool health")
    test("GET /tools/health", lambda: get("/tools/health")["status"] == "ok")
    print()

    # ── 7. Transaction Persistence ───────────────────────────────────
    print("7. Transaction persistence")
    import sqlite3
    conn = sqlite3.connect("paari.db")
    tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    test(f"Transactions table has rows ({tx_count} found)", lambda: tx_count > 0)
    audit_count = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    test(f"Audit events table has rows ({audit_count} found)", lambda: audit_count > 0)
    conn.close()
    print()

    # ── Summary ──────────────────────────────────────────────────────
    print("=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
